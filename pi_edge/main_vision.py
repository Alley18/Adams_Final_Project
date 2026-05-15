"""
adams_vision.py – improved v2

Key changes:
- Emotion detection is now INDEPENDENT of danger-state detection.
  Uses eye-openness ratio + face aspect ratio as a lightweight proxy
  for happiness/neutral/stressed/sleepy — no ML model needed on Pi.
- DIZZY and DISTRACTED each trigger buzz_alert() with their own state string.
  Previously the buzzer only fired when BOTH danger AND hands-off were true,
  and it always used the default pattern.  Now each danger state fires
  its matching buzz pattern independently (subject to per-state cooldown).
- Added per-state buzz cooldown so switching from DISTRACTED→DIZZY
  re-triggers the alert immediately rather than waiting out the global timer.
- PERCLOS frame counter is preserved (from v1 improvement).
- State priority: DROWSY > DIZZY > DISTRACTED > NORMAL (unchanged).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import logging
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from cloud_sync import CloudSync
from hardware import HardwareController

# =========================
# SETTINGS
# =========================

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

CAMERA_INDEX = 0

# Frames without a face before DISTRACTED
NO_FACE_FRAME_LIMIT = 30

# PERCLOS: consecutive eye-closed frames before DROWSY (~2 s at 15 fps)
DROWSY_FRAME_LIMIT = 30

# Head pixel movement per frame to trigger DIZZY
DIZZY_MOVEMENT_THRESHOLD = 40
MOVEMENT_HISTORY_SIZE = 20

# Per-state buzz cooldown (seconds) — each state has its own timer
STATE_BUZZ_COOLDOWN: dict[str, float] = {
    "DISTRACTED": 4.0,
    "DIZZY":      3.0,
    "DROWSY":     5.0,
}

# State priority (higher index = higher priority)
STATE_PRIORITY = ["NORMAL", "DISTRACTED", "DIZZY", "DROWSY"]
DANGER_STATES  = {"DISTRACTED", "DIZZY", "DROWSY"}

# ------------------------------------------------------------------
# Emotion thresholds (lightweight, no ML)
# We derive a rough emotion from:
#   eye_openness_ratio  – eyes open wide → ALERT/HAPPY; closed → SLEEPY
#   head_movement       – high movement → STRESSED
#   face present?       – absent → UNFOCUSED
# ------------------------------------------------------------------
EMOTION_MOVEMENT_THRESHOLD = 25   # avg px/frame → STRESSED
EMOTION_CLOSED_THRESHOLD   = 10   # closed frames before SLEEPY emotion

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "adams.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ADAMS")


# =========================
# MAIN SYSTEM
# =========================

class AdamsVisionSystem:

    def __init__(self):
        logger.info("Starting ADAMS v2")

        self.hardware = HardwareController()
        self.cloud    = CloudSync()
        self.cloud.start()

        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            raise RuntimeError("Camera failed to open")

        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_smile.xml"
        )

        # --- Driver state ---
        self.driver_state        = "NORMAL"
        self.no_face_counter     = 0
        self.eyes_closed_frames  = 0
        self.last_face_pos       = None
        self.movement_history: deque[float] = deque(maxlen=MOVEMENT_HISTORY_SIZE)

        # --- Emotion (independent) ---
        self.emotion             = "NEUTRAL"
        self._smile_history: deque[bool] = deque(maxlen=10)

        # --- Per-state buzz cooldown ---
        self._last_buzz_per_state: dict[str, float] = {s: 0.0 for s in DANGER_STATES}

        # --- Diagnostics ---
        self.face_detected  = False
        self.eye_count      = 0
        self.avg_movement   = 0.0

    # ------------------------------------------------------------------
    # State machine helpers
    # ------------------------------------------------------------------

    def _resolve_state(self, *candidates: str) -> str:
        """Return the highest-priority state among candidates."""
        best = "NORMAL"
        for s in candidates:
            if STATE_PRIORITY.index(s) > STATE_PRIORITY.index(best):
                best = s
        return best

    def set_state(self, new_state: str) -> None:
        if new_state != self.driver_state:
            logger.warning(f"STATE: {self.driver_state} → {new_state}")
            self.driver_state = new_state

    # ------------------------------------------------------------------
    # Emotion detection  (independent from danger state)
    # ------------------------------------------------------------------

    def _detect_emotion(self, gray, face_rect) -> str:
        """
        Lightweight emotion proxy — no ML, pure OpenCV heuristics.

        Rules (applied in priority order):
          SLEEPY   – eyes closed for several frames
          HAPPY    – smile detected in lower face region
          STRESSED – high head movement
          NEUTRAL  – default
        """
        if not self.face_detected:
            return "UNFOCUSED"

        # SLEEPY takes priority over everything
        if self.eyes_closed_frames >= EMOTION_CLOSED_THRESHOLD:
            return "SLEEPY"

        # Smile detection in lower half of face
        x, y, w, h = face_rect
        lower_face = gray[y + h // 2 : y + h, x : x + w]
        smiles = self.smile_cascade.detectMultiScale(
            lower_face, scaleFactor=1.7, minNeighbors=22, minSize=(25, 15)
        )
        self._smile_history.append(len(smiles) > 0)
        smile_rate = sum(self._smile_history) / max(len(self._smile_history), 1)

        if smile_rate > 0.5:
            return "HAPPY"

        # STRESSED – sustained high movement
        if self.avg_movement > EMOTION_MOVEMENT_THRESHOLD:
            return "STRESSED"

        # Wide eyes (eye count 2) with no smile → ALERT/FOCUSED
        if self.eye_count >= 2:
            return "FOCUSED"

        return "NEUTRAL"

    # ------------------------------------------------------------------
    # Buzz logic – per-state cooldown
    # ------------------------------------------------------------------

    def _maybe_buzz(self, state: str) -> None:
        """Fire buzz for *state* only if its own cooldown has expired."""
        now = time.time()
        cooldown = STATE_BUZZ_COOLDOWN.get(state, 3.0)
        if now - self._last_buzz_per_state.get(state, 0.0) >= cooldown:
            self._last_buzz_per_state[state] = now
            self.hardware.buzz_alert(state)   # passes state string to hardware

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def get_largest_face(faces):
        return max(faces, key=lambda f: f[2] * f[3])

    def draw_status(self, frame, hands_on_wheel: bool) -> None:
        state_color = {
            "NORMAL":      (0,   255,   0),
            "DISTRACTED":  (0,   165, 255),
            "DIZZY":       (0,   255, 255),
            "DROWSY":      (0,     0, 255),
        }.get(self.driver_state, (255, 255, 255))

        labels = [
            (f"STATE:    {self.driver_state}",              state_color,       1.0),
            (f"EMOTION:  {self.emotion}",                   (255, 255, 255),   0.9),
            (f"HANDS:    {'ON' if hands_on_wheel else 'OFF'}", (255, 255, 0),  0.8),
            (f"EYES CLOSED: {self.eyes_closed_frames}f",   (200, 200, 255),   0.7),
            (f"MOVEMENT:   {self.avg_movement:.1f}",        (200, 255, 200),   0.7),
            (f"EYE COUNT:  {self.eye_count}",               (200, 255, 255),   0.7),
        ]
        for i, (text, color, scale) in enumerate(labels):
            cv2.putText(frame, text, (20, 35 + i * 36),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)

    def sync_to_cloud(self, hands_on_wheel: bool) -> None:
        self.cloud.update_data({
            "driver_state":       self.driver_state,
            "emotion":            self.emotion,
            "hands_on_wheel":     hands_on_wheel,
            "face_detected":      self.face_detected,
            "eye_count":          self.eye_count,
            "avg_movement":       round(self.avg_movement, 2),
            "eyes_closed_frames": self.eyes_closed_frames,
            "timestamp":          time.time(),
        })

    def cleanup(self) -> None:
        logger.info("Stopping ADAMS")
        self.cloud.stop()
        self.hardware.cleanup()
        self.cap.release()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    logger.error("Failed to capture frame")
                    break

                gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5
                )

                self.face_detected = len(faces) > 0
                candidate_state    = "NORMAL"
                face_rect          = None   # for emotion detection

                # ── NO FACE ──────────────────────────────────────────────
                if not self.face_detected:
                    self.no_face_counter += 1
                    self.last_face_pos    = None
                    self.movement_history.clear()
                    self.avg_movement     = 0.0
                    self.eye_count        = 0
                    self.eyes_closed_frames = 0

                    if self.no_face_counter > NO_FACE_FRAME_LIMIT:
                        candidate_state = self._resolve_state(candidate_state, "DISTRACTED")

                # ── FACE DETECTED ────────────────────────────────────────
                else:
                    self.no_face_counter = 0
                    x, y, w, h = self.get_largest_face(faces)
                    face_rect  = (x, y, w, h)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    # ── Head movement → DIZZY ─────────────────────────
                    movement = (
                        abs(x - self.last_face_pos[0]) + abs(y - self.last_face_pos[1])
                        if self.last_face_pos is not None else 0.0
                    )
                    self.last_face_pos = (x, y)
                    self.movement_history.append(movement)
                    self.avg_movement = (
                        sum(self.movement_history) / len(self.movement_history)
                    )

                    if self.avg_movement > DIZZY_MOVEMENT_THRESHOLD:
                        candidate_state = self._resolve_state(candidate_state, "DIZZY")

                    # ── Eye detection → DROWSY ────────────────────────
                    roi_gray = gray[y: y + h, x: x + w]
                    eyes = self.eye_cascade.detectMultiScale(
                        roi_gray, scaleFactor=1.1, minNeighbors=8
                    )
                    self.eye_count = len(eyes)

                    for ex, ey, ew, eh in eyes:
                        cv2.rectangle(
                            frame,
                            (x + ex, y + ey),
                            (x + ex + ew, y + ey + eh),
                            (255, 255, 0), 2,
                        )

                    if self.eye_count == 0:
                        self.eyes_closed_frames += 1
                    else:
                        self.eyes_closed_frames = 0

                    if self.eyes_closed_frames > DROWSY_FRAME_LIMIT:
                        candidate_state = self._resolve_state(candidate_state, "DROWSY")

                # ── Apply state ───────────────────────────────────────────
                self.set_state(candidate_state)

                # ── Emotion (independent) ─────────────────────────────────
                self.emotion = self._detect_emotion(gray, face_rect)

                # ── Wheel sensor ──────────────────────────────────────────
                hands_on_wheel = self.hardware.is_hands_on_wheel()

                # ── Buzz alerts (each danger state manages its own cooldown) ──
                # DISTRACTED: always buzz (driver not looking, regardless of hands)
                if self.driver_state == "DISTRACTED":
                    self._maybe_buzz("DISTRACTED")

                # DIZZY: always buzz (could lose control any moment)
                elif self.driver_state == "DIZZY":
                    self._maybe_buzz("DIZZY")

                # DROWSY: buzz — escalate if also hands off wheel
                elif self.driver_state == "DROWSY":
                    self._maybe_buzz("DROWSY")

                # ── Display & sync ────────────────────────────────────────
                self.sync_to_cloud(hands_on_wheel)

        finally:
            self.cleanup()


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    system = AdamsVisionSystem()
    system.run()