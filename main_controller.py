"""
ADAMS Vision Pipeline
=====================
Stable conversational mode architecture.

Version: 4.1.0
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("adams.pipeline")

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

EMOTION_INTERVAL = 5.0

AI_COOLDOWN_DROWSY = 20.0
AI_COOLDOWN_DISTRACTED = 18.0
AI_COOLDOWN_EMOTION = 40.0

DROWSY_CONFIRM_SEC = 4.5
DISTRACTION_CONFIRM_SEC = 3.5

VOICE_ALERT_COOLDOWN = 12.0

CONVERSATION_TIMEOUT = 10.0

CAMERA_INDEX = 0

CURRENT_POSITION = (126.9780, 37.5665)
DESTINATION = (127.0276, 37.4979)

EMOTION_MAP = {
    "angry": "Angry",
    "disgust": "Angry",
    "fear": "Stressed",
    "sad": "Stressed",
    "happy": "Happy",
    "surprise": "Neutral",
    "neutral": "Neutral",
}

HIGH_RISK_EMOTIONS = frozenset({
    "Angry",
    "Stressed",
})


# ------------------------------------------------------------------
# ENUMS
# ------------------------------------------------------------------

class AlertTrigger(Enum):

    DROWSY = auto()
    DISTRACTED = auto()
    EMOTION = auto()


class SystemMode(Enum):

    DRIVING = auto()
    CONVERSATION = auto()


# ------------------------------------------------------------------
# STATE
# ------------------------------------------------------------------

@dataclass
class PipelineState:

    mode: SystemMode = SystemMode.DRIVING

    current_emotion: str = "Neutral"
    current_confidence: float = 0.0

    last_emotion_time: float = 0.0
    last_voice_alert: float = 0.0

    last_ai_time_drowsy: float = 0.0
    last_ai_time_distracted: float = 0.0
    last_ai_time_emotion: float = 0.0

    last_driver_chat: float = 0.0

    drowsy_since: Optional[float] = None
    distracted_since: Optional[float] = None


# ------------------------------------------------------------------
# MAIN PIPELINE
# ------------------------------------------------------------------

class AdamsVisionPipeline:

    def __init__(self):

        logger.info(
            "Initializing ADAMS Vision Pipeline v4.1"
        )

        self.eye_detector = EyeDetector()

        self.brain = AdamsBrain()

        self.voice = AdamsVoice()

        self.ears = AdamsEars()

        self.state = PipelineState()

        self._lock = threading.Lock()

        self._speaking_lock = threading.Lock()

        self._driver_talking = False

    # --------------------------------------------------------------
    # SAFE SPEAKING
    # --------------------------------------------------------------

    def _speak_safely(self, text):

        with self._speaking_lock:

            try:

                logger.info("Ears paused before speaking")
                self.ears.pause()

                time.sleep(0.5)

                logger.info("Speaking started")
                self.voice.speak(text)

                self.voice.wait_until_done(timeout=20.0)

                logger.info("Speaking finished")

                time.sleep(1.5)

            finally:

                logger.info("Ears resumed after speaking")
                self.ears.resume()

    def _alert_safely(self, text):

        with self._speaking_lock:

            try:

                logger.info("Ears paused before alert")
                self.ears.pause()

                time.sleep(0.5)

                logger.info("Speaking started")
                self.voice.alert(text)

                self.voice.wait_until_done(timeout=20.0)

                logger.info("Speaking finished")

                time.sleep(1.5)

            finally:

                logger.info("Ears resumed after alert")
                self.ears.resume()

    # --------------------------------------------------------------
    # DRIVER CHAT
    # --------------------------------------------------------------

    def _on_driver_speech(self, text):

        logger.info("Callback fired")

        logger.info(
            "Driver command: %r",
            text,
        )

        if self.state.mode != SystemMode.CONVERSATION:
            logger.info("Entering conversation mode")

        self.state.mode = SystemMode.CONVERSATION
        self.ears.conversation_active = True

        self._driver_talking = True

        now = time.time()
        self.state.last_driver_chat = now
        self.ears.last_conversation_time = now

        threading.Thread(
            target=self._process_chat,
            args=(text,),
            daemon=True,
        ).start()

    def _process_chat(self, text):

        try:

            if self.voice.is_speaking:
                self.voice.stop()

            logger.info(
                "brain.chat(%r)",
                text,
            )

            reply = self.brain.chat(text)

            if not reply:
                reply = (
                    "Sorry, I didn't understand that."
                )

            print(f"🤖 ADAMS: {reply}")

            self._speak_safely(reply)

        except Exception as exc:

            logger.exception(
                "Chat failed: %s",
                exc,
            )

            self._speak_safely(
                "I had a problem processing that."
            )

        finally:

            self._driver_talking = False

            self.state.last_driver_chat = time.time()

    # --------------------------------------------------------------
    # EMOTION DETECTION
    # --------------------------------------------------------------

    def _run_emotion_detection(self, frame_copy):

        def detect():

            try:

                results = DeepFace.analyze(
                    frame_copy,
                    actions=["emotion"],
                    enforce_detection=False,
                    silent=True,
                )

                res = (
                    results[0]
                    if isinstance(results, list)
                    else results
                )

                label = res["dominant_emotion"]

                with self._lock:

                    self.state.current_emotion = (
                        EMOTION_MAP.get(
                            label,
                            "Neutral",
                        )
                    )

                    self.state.current_confidence = (
                        float(
                            res["emotion"][label]
                        )
                    )

            except Exception as exc:

                logger.debug(
                    "Emotion detection failed: %s",
                    exc,
                )

        threading.Thread(
            target=detect,
            daemon=True,
        ).start()

    # --------------------------------------------------------------
    # AI RESPONSE
    # --------------------------------------------------------------

    def _trigger_ai_response(
        self,
        eye_data,
        trigger,
    ):

        if self.ears.conversation_active:
            logger.info(
                "AI blocked due to conversation mode: %s",
                trigger.name,
            )
            return

        def respond():

            if self.ears.conversation_active:
                logger.info(
                    "AI blocked due to conversation mode: %s",
                    trigger.name,
                )
                return

            if (
                self.state.mode
                != SystemMode.DRIVING
            ):
                return

            if self.voice.is_speaking:
                return

            try:

                telemetry = (
                    f"Trigger: {trigger.name}, "
                    f"Emotion: {self.state.current_emotion}, "
                    f"Eye openness: "
                    f"{self._safe_eye_pct(eye_data)}%"
                )

                raw = self.brain.generate_advice(
                    telemetry
                )

                data = json.loads(raw)

                msg = data.get(
                    "message",
                    "Please stay focused.",
                )

                route = data.get(
                    "suggested_route",
                    "FASTEST",
                )

                self._alert_safely(msg)

                if route in (
                    "REST_STOP",
                    "SCENIC",
                ):

                    time.sleep(0.5)

                    route_text = (
                        route_summary_for_adams(
                            route,
                            CURRENT_POSITION,
                            DESTINATION,
                        )
                    )

                    if route_text:

                        self._speak_safely(
                            route_text
                        )

            except Exception as exc:

                logger.exception(
                    "AI response failed: %s",
                    exc,
                )

        threading.Thread(
            target=respond,
            daemon=True,
        ).start()

    # --------------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------------

    @staticmethod
    def _safe_eye_pct(eye_data):

        return int(
            float(
                eye_data.get(
                    "eye_opening",
                    0.0,
                )
            ) * 100
        )

    # --------------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------------

    def run(self):

        cap = cv2.VideoCapture(
            CAMERA_INDEX,
            cv2.CAP_DSHOW,
        )

        if not cap.isOpened():

            logger.critical(
                "Camera failed to open"
            )

            return

        self.voice.speak(
            "ADAMS online. "
            "Say Hey Adams to talk to me."
        )

        time.sleep(2)

        self.ears.start(
            callback=self._on_driver_speech
        )

        logger.info("Pipeline running")

        while True:

            ret, frame = cap.read()

            if not ret:
                break

            now = time.time()

            if (
                self.ears.conversation_active
                and self.state.mode
                != SystemMode.CONVERSATION
            ):

                logger.info("Entering conversation mode")

                self.state.mode = (
                    SystemMode.CONVERSATION
                )

                self.state.last_driver_chat = max(
                    self.state.last_driver_chat,
                    self.ears.last_conversation_time,
                )

            eye_data = self.eye_detector.analyze(
                frame
            )

            # --------------------------------------------------
            # CONVERSATION MODE
            # --------------------------------------------------

            if (
                self.state.mode
                == SystemMode.CONVERSATION
            ):

                silence_time = (
                    now
                    - max(
                        self.state.last_driver_chat,
                        self.ears.last_conversation_time,
                    )
                )

                if (
                    silence_time
                    > CONVERSATION_TIMEOUT
                ):

                    logger.info(
                        "Leaving conversation mode"
                    )

                    self.state.mode = (
                        SystemMode.DRIVING
                    )
                    self.ears.conversation_active = False

                else:

                    self._draw_hud(
                        frame,
                        eye_data,
                    )

                    if (
                        cv2.waitKey(1)
                        & 0xFF
                    ) in (
                        ord("q"),
                        27,
                    ):
                        break

                    continue

            # --------------------------------------------------
            # DRIVING MODE
            # --------------------------------------------------

            if (
                now
                - self.state.last_emotion_time
            ) > EMOTION_INTERVAL:

                self._run_emotion_detection(
                    frame.copy()
                )

                self.state.last_emotion_time = (
                    now
                )

            # --------------------------------------------------
            # BASIC ALERTS
            # --------------------------------------------------

            voice_ready = (
                now
                - self.state.last_voice_alert
            ) > VOICE_ALERT_COOLDOWN

            if (
                voice_ready
                and not self.voice.is_speaking
                and not self.ears.conversation_active
            ):

                if eye_data.get("is_drowsy"):

                    self.state.last_voice_alert = (
                        now
                    )

                    threading.Thread(
                        target=self._alert_safely,
                        args=(
                            "Wake up! Focus on the road.",
                        ),
                        daemon=True,
                    ).start()

                elif eye_data.get(
                    "is_distracted"
                ):

                    self.state.last_voice_alert = (
                        now
                    )

                    threading.Thread(
                        target=self._alert_safely,
                        args=(
                            "Eyes on the road!",
                        ),
                        daemon=True,
                    ).start()

            # --------------------------------------------------
            # DROWSY TRACKING
            # --------------------------------------------------

            if eye_data.get("is_drowsy"):

                if not self.state.drowsy_since:

                    self.state.drowsy_since = now

            else:

                self.state.drowsy_since = None

            # --------------------------------------------------
            # DISTRACTION TRACKING
            # --------------------------------------------------

            if eye_data.get(
                "is_distracted"
            ):

                if not self.state.distracted_since:

                    self.state.distracted_since = (
                        now
                    )

            else:

                self.state.distracted_since = None

            # --------------------------------------------------
            # FULL AI RESPONSES
            # --------------------------------------------------

            if (
                self.state.drowsy_since
                and (
                    now
                    - self.state.drowsy_since
                ) > DROWSY_CONFIRM_SEC
                and (
                    now
                    - self.state.last_ai_time_drowsy
                ) > AI_COOLDOWN_DROWSY
            ):

                self._trigger_ai_response(
                    eye_data,
                    AlertTrigger.DROWSY,
                )

                self.state.last_ai_time_drowsy = (
                    now
                )

            if (
                self.state.distracted_since
                and (
                    now
                    - self.state.distracted_since
                ) > DISTRACTION_CONFIRM_SEC
                and (
                    now
                    - self.state.last_ai_time_distracted
                ) > AI_COOLDOWN_DISTRACTED
            ):

                self._trigger_ai_response(
                    eye_data,
                    AlertTrigger.DISTRACTED,
                )

                self.state.last_ai_time_distracted = (
                    now
                )

            if (
                self.state.current_emotion
                in HIGH_RISK_EMOTIONS
                and (
                    now
                    - self.state.last_ai_time_emotion
                ) > AI_COOLDOWN_EMOTION
            ):

                self._trigger_ai_response(
                    eye_data,
                    AlertTrigger.EMOTION,
                )

                self.state.last_ai_time_emotion = (
                    now
                )

            self._draw_hud(
                frame,
                eye_data,
            )

            if (
                cv2.waitKey(1)
                & 0xFF
            ) in (
                ord("q"),
                27,
            ):
                break

        logger.info("Shutting down")

        self.ears.stop()

        self.voice.stop()

        cap.release()

        cv2.destroyAllWindows()

    # --------------------------------------------------------------
    # HUD
    # --------------------------------------------------------------

    def _draw_hud(
        self,
        frame,
        eye_data,
    ):

        display = (
            self.eye_detector.draw_overlay(
                frame,
                eye_data,
            )
        )

        mode_text = (
            f"Mode: "
            f"{self.state.mode.name}"
        )

        cv2.putText(
            display,
            mode_text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )

        cv2.putText(
            display,
            f"Emotion: "
            f"{self.state.current_emotion}",
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
        )

        cv2.imshow(
            "ADAMS Driver Monitor",
            display,
        )


# ------------------------------------------------------------------
# ENTRY
# ------------------------------------------------------------------

if __name__ == "__main__":

    AdamsVisionPipeline().run()
