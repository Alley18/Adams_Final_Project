"""
ADAMS Vision Pipeline
=====================
Authors : ADAMS Team
Version : 3.3.0

Changes vs 3.2:
  - _on_driver_speech now logs immediately so we can see in terminal
    exactly when a command arrives and whether brain.chat() was called.
  - Chat lockout check moved AFTER logging so we always see what was heard.
  - Overpass timeout reduced to 5 s (was 8) so route fallback fires faster.
"""

import cv2
import time
import json
import sys
import os
import threading
import logging

from dataclasses import dataclass
from typing import Optional
from enum import Enum, auto

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

from deepface import DeepFace

from backend.detection.face_mesh import EyeDetector
from ai_engine.brain import AdamsBrain
from ai_engine.adams_voice import AdamsVoice
from ai_engine.adams_ears import AdamsEars
from ai_engine.adams_route import route_summary_for_adams
from ai_engine.logger import log_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("adams.pipeline")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EMOTION_INTERVAL        = 5.0
AI_COOLDOWN_DROWSY      = 12.0
AI_COOLDOWN_DISTRACTED  = 10.0
AI_COOLDOWN_EMOTION     = 30.0
DROWSY_CONFIRM_SEC      = 2.5
DISTRACTION_CONFIRM_SEC = 2.0
VOICE_ALERT_COOLDOWN    = 6.0
CHAT_LOCKOUT_SEC        = 5.0
CAMERA_INDEX            = 0

CURRENT_POSITION = (126.9780, 37.5665)
DESTINATION      = (127.0276, 37.4979)

EMOTION_MAP = {
    "angry":   "Angry",
    "disgust": "Angry",
    "fear":    "Stressed",
    "sad":     "Stressed",
    "happy":   "Happy",
    "surprise":"Neutral",
    "neutral": "Neutral",
}

HIGH_RISK_EMOTIONS = frozenset({"Angry", "Stressed"})


class AlertTrigger(Enum):
    DROWSY     = auto()
    DISTRACTED = auto()
    EMOTION    = auto()


@dataclass
class PipelineState:
    current_emotion:    str   = "Neutral"
    current_confidence: float = 0.0

    last_emotion_time:       float = 0.0
    last_voice_alert:        float = 0.0
    last_ai_time_drowsy:     float = 0.0
    last_ai_time_distracted: float = 0.0
    last_ai_time_emotion:    float = 0.0
    last_driver_chat:        float = 0.0

    drowsy_since:     Optional[float] = None
    distracted_since: Optional[float] = None


class AdamsVisionPipeline:

    def __init__(self) -> None:
        logger.info("Initialising ADAMS Vision Pipeline v3.3...")

        self.eye_detector    = EyeDetector()
        self.brain           = AdamsBrain()
        self.voice           = AdamsVoice()
        self.ears            = AdamsEars()
        self.state           = PipelineState()
        self._lock           = threading.Lock()
        self._driver_talking = False

    # ------------------------------------------------------------------
    # Speaking
    # ------------------------------------------------------------------

    def _speak_safely(self, text: str) -> None:
        try:
            self.ears.pause()
            self.voice.speak(text)
            deadline = time.time() + 15
            while self.voice.is_speaking and time.time() < deadline:
                time.sleep(0.15)
        except Exception as exc:
            logger.error("_speak_safely: %s", exc)
        finally:
            self.ears.resume()

    def _alert_safely(self, text: str) -> None:
        try:
            self.ears.pause()
            self.voice.alert(text)
            deadline = time.time() + 15
            while self.voice.is_speaking and time.time() < deadline:
                time.sleep(0.15)
        except Exception as exc:
            logger.error("_alert_safely: %s", exc)
        finally:
            self.ears.resume()

    # ------------------------------------------------------------------
    # Driver speech
    # ------------------------------------------------------------------

    def _on_driver_speech(self, text: str) -> None:
        # Always log first — this confirms the callback fired
        logger.info("🎙️ Driver command received: %r", text)
        print(f"🎙️ Driver command: {text}")

        # Mark conversation active
        self._driver_talking = True
        self.state.last_driver_chat = time.time()

        threading.Thread(
            target=self._process_chat,
            args=(text,),
            daemon=True,
        ).start()

    def _process_chat(self, text: str) -> None:
        try:
            # Stop any background speech so our reply isn't buried
            if self.voice.is_speaking:
                self.voice.alert("")

            logger.info("→ brain.chat(%r)", text)
            reply = self.brain.chat(text)
            logger.info("← brain replied: %r", reply[:100] if reply else "EMPTY")

            if not reply or not reply.strip():
                reply = "Sorry, I didn't catch that."

            print(f"🤖 ADAMS: {reply}")
            self._speak_safely(reply)

        except Exception as exc:
            logger.error("_process_chat failed: %s", exc, exc_info=True)
            self._speak_safely("I had a problem with that — sorry.")
        finally:
            self.state.last_driver_chat = time.time()
            self._driver_talking = False

    def _in_chat_lockout(self) -> bool:
        return (
            self._driver_talking
            or (time.time() - self.state.last_driver_chat) < CHAT_LOCKOUT_SEC
        )

    # ------------------------------------------------------------------
    # Emotion
    # ------------------------------------------------------------------

    def _run_emotion_detection(self, frame_copy) -> None:
        def _detect():
            try:
                results = DeepFace.analyze(
                    frame_copy, actions=["emotion"],
                    enforce_detection=False, silent=True,
                )
                res   = results[0] if isinstance(results, list) else results
                label = res["dominant_emotion"]
                with self._lock:
                    self.state.current_emotion    = EMOTION_MAP.get(label, "Neutral")
                    self.state.current_confidence = float(res["emotion"][label])
            except Exception as exc:
                logger.debug("Emotion detection: %s", exc)

        threading.Thread(target=_detect, daemon=True).start()

    # ------------------------------------------------------------------
    # AI safety response
    # ------------------------------------------------------------------

    def _trigger_ai_response(self, eye_data: dict, trigger: AlertTrigger) -> None:
        def _respond():
            if self._in_chat_lockout() or self.voice.is_speaking:
                logger.debug("Trigger %s suppressed (lockout or speaking).", trigger.name)
                return
            try:
                telemetry = (
                    f"Trigger: {trigger.name}, "
                    f"Emotion: {self.state.current_emotion}, "
                    f"Eye openness: {self._safe_eye_pct(eye_data)}%"
                )
                raw_response = self.brain.generate_advice(telemetry)
                data         = json.loads(raw_response)
                msg          = data.get("message", "Please stay focused.")
                route        = data.get("suggested_route", "FASTEST")

                self._log_event(
                    trigger.name, data.get("level", "WARNING"),
                    msg, eye_data, data.get("buzzer_active", False), raw_response,
                )
                self._alert_safely(msg)

                if route in ("REST_STOP", "SCENIC"):
                    time.sleep(0.5)
                    route_text = route_summary_for_adams(route, CURRENT_POSITION, DESTINATION)
                    if route_text:
                        self._speak_safely(route_text)

            except Exception as exc:
                logger.error("AI response failed: %s", exc, exc_info=True)

        threading.Thread(target=_respond, daemon=True).start()

    # ------------------------------------------------------------------
    # Logging / helpers
    # ------------------------------------------------------------------

    def _log_event(self, trigger, level, message, eye_data, buzzer, raw_res="") -> None:
        event = {
            "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
            "trigger":       trigger, "level": level, "message": message,
            "eye_opening":   self._safe_eye_pct(eye_data),
            "is_drowsy":     bool(eye_data.get("is_drowsy", False)),
            "is_distracted": bool(eye_data.get("is_distracted", False)),
            "yaw_deg":       float(eye_data.get("yaw_deg", 0.0)),
            "emotion":       self.state.current_emotion,
        }
        try:
            log_event(json.dumps(event), raw_res or json.dumps({"message": message}))
        except Exception as exc:
            logger.error("Logging failed: %s", exc)

    @staticmethod
    def _safe_eye_pct(eye_data: dict) -> int:
        return int(float(eye_data.get("eye_opening", 0.0)) * 100)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        if not cap.isOpened():
            logger.critical("Camera failed to open.")
            return

        self.voice.speak("ADAMS online. Say Hey Adams to talk to me.")
        time.sleep(2)

        self.ears.start(callback=self._on_driver_speech)
        logger.info("Pipeline running. Press Q to quit.")

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            now      = time.time()
            eye_data = self.eye_detector.analyze(frame)

            # Emotion detection
            if now - self.state.last_emotion_time > EMOTION_INTERVAL:
                self._run_emotion_detection(frame.copy())
                self.state.last_emotion_time = now

            # Skip background alerts while driver is in a conversation
            if self._in_chat_lockout():
                self._draw_hud(frame, eye_data)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
                continue

            # Immediate voice alerts
            voice_ready = (now - self.state.last_voice_alert) > VOICE_ALERT_COOLDOWN
            if voice_ready and not self.voice.is_speaking:
                if eye_data.get("is_drowsy"):
                    self.state.last_voice_alert = now
                    threading.Thread(
                        target=self._alert_safely,
                        args=("Wake up! Please focus on the road.",),
                        daemon=True,
                    ).start()
                elif eye_data.get("is_distracted"):
                    self.state.last_voice_alert = now
                    threading.Thread(
                        target=self._alert_safely,
                        args=("Eyes on the road!",),
                        daemon=True,
                    ).start()

            # Drowsiness tracking
            if eye_data.get("is_drowsy"):
                if not self.state.drowsy_since:
                    self.state.drowsy_since = now
            else:
                self.state.drowsy_since = None

            # Distraction tracking
            if eye_data.get("is_distracted"):
                if not self.state.distracted_since:
                    self.state.distracted_since = now
            else:
                self.state.distracted_since = None

            # Sustained drowsiness → full AI response
            if (
                not self.voice.is_speaking
                and self.state.drowsy_since
                and (now - self.state.drowsy_since)        > DROWSY_CONFIRM_SEC
                and (now - self.state.last_ai_time_drowsy) > AI_COOLDOWN_DROWSY
            ):
                self._trigger_ai_response(eye_data, AlertTrigger.DROWSY)
                self.state.last_ai_time_drowsy = now

            # Sustained distraction → full AI response
            if (
                not self.voice.is_speaking
                and self.state.distracted_since
                and (now - self.state.distracted_since)        > DISTRACTION_CONFIRM_SEC
                and (now - self.state.last_ai_time_distracted) > AI_COOLDOWN_DISTRACTED
            ):
                self._trigger_ai_response(eye_data, AlertTrigger.DISTRACTED)
                self.state.last_ai_time_distracted = now

            # High-risk emotion → AI response
            if (
                not self.voice.is_speaking
                and self.state.current_emotion in HIGH_RISK_EMOTIONS
                and (now - self.state.last_ai_time_emotion) > AI_COOLDOWN_EMOTION
            ):
                self._trigger_ai_response(eye_data, AlertTrigger.EMOTION)
                self.state.last_ai_time_emotion = now

            self._draw_hud(frame, eye_data)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

        logger.info("Shutting down ADAMS...")
        self.ears.stop()
        self.voice.stop()
        cap.release()
        cv2.destroyAllWindows()
        logger.info("ADAMS shut down cleanly.")

    def _draw_hud(self, frame, eye_data) -> None:
        display = self.eye_detector.draw_overlay(frame, eye_data)
        cv2.putText(display, f"State: {self.state.current_emotion}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        status = "💬 Talking..." if self._driver_talking else "Say 'Hey Adams' to talk"
        cv2.putText(display, status,
                    (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.imshow("ADAMS Driver Monitor", display)


if __name__ == "__main__":
    AdamsVisionPipeline().run()