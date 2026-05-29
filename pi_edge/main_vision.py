"""
main_vision.py – ADAMS v3
Laptop AI Vision System

Features:
- DISTRACTED detection using head direction
- DIZZY detection using unstable head sway
- DROWSY detection using EAR (Eye Aspect Ratio)
- Emotion detection separated from danger states
- Firebase cloud sync
- Raspberry Pi buzzer trigger through Firebase
- MediaPipe FaceMesh based tracking

Danger states:
    NORMAL
    DISTRACTED
    DIZZY
    DROWSY

Emotion states:
    HAPPY
    STRESSED
    FOCUSED
    SLEEPY
    NEUTRAL
"""

import cv2
import time
import math
import logging
import numpy as np
from hardware import HardwareController

from pathlib import Path
from collections import deque

import mediapipe as mp

from cloud_sync import CloudSync


# =========================================================
# SETTINGS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

CAMERA_INDEX = 1

# -------------------------------
# Drowsiness
# -------------------------------

EAR_THRESHOLD = 0.18
DROWSY_FRAME_LIMIT = 35

# -------------------------------
# Distraction
# -------------------------------

DISTRACTION_ANGLE = 10

# -------------------------------
# Dizziness
# -------------------------------

MOVEMENT_HISTORY_SIZE = 20
DIZZY_SWAY_THRESHOLD = 6
HANDS_LOG_INTERVAL_SECONDS = 5

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "adams.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("ADAMS")


# =========================================================
# MEDIAPIPE
# =========================================================

mp_face_mesh = mp.solutions.face_mesh

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


# =========================================================
# MAIN SYSTEM
# =========================================================

class AdamsVisionSystem:

    def __init__(self):

        logger.info("Starting ADAMS v3")

        self.hardware = HardwareController()

        # hands_on_wheel is owned by the Pi (guardian_dart.py reads
        # the FSR directly). The laptop has no GPIO so we always send
        # True here — the Pi overrides it with the real sensor value.
        self.hands_on_wheel = True

        self.cloud = CloudSync()
        self.cloud.start()

        self.cap = cv2.VideoCapture(CAMERA_INDEX)

        if not self.cap.isOpened():
            raise RuntimeError("Camera failed to open")

        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        # -------------------------------
        # Driver state
        # -------------------------------

        self.driver_state = "NORMAL"

        self.emotion = "NEUTRAL"

        self.eyes_closed_frames = 0

        self.face_detected = False

        self.eye_count = 2

        self.avg_movement = 0.0

        self.sway_score = 0.0

        self.last_nose = None

        self.movement_history = deque(maxlen=MOVEMENT_HISTORY_SIZE)

    # =====================================================
    # Utilities
    # =====================================================

    def eye_aspect_ratio(self, eye):

        vertical1 = np.linalg.norm(eye[1] - eye[5])
        vertical2 = np.linalg.norm(eye[2] - eye[4])

        horizontal = np.linalg.norm(eye[0] - eye[3])

        return (vertical1 + vertical2) / (2.0 * horizontal)

    def set_state(self, new_state):

        if new_state != self.driver_state:

            logger.warning(
                f"STATE: {self.driver_state} -> {new_state}"
            )

            self.driver_state = new_state

    def draw_text(self, frame, text, y, color):

        cv2.putText(
            frame,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )

    # =====================================================
    # Emotion
    # =====================================================

    def detect_emotion(self):

        if self.driver_state == "DROWSY":
            return "SLEEPY"

        if self.driver_state == "DIZZY":
            return "STRESSED"

        if self.driver_state == "DISTRACTED":
            return "UNFOCUSED"

        if self.eye_count >= 2:
            return "FOCUSED"

        return "NEUTRAL"

    # =====================================================
    # Firebase Sync
    # =====================================================

    def sync_to_cloud(self):

        self.cloud.update_data({

            "driver_state": self.driver_state,

            "emotion": self.emotion,

            "face_detected": self.face_detected,

            "eye_count": self.eye_count,

            "avg_movement": round(self.avg_movement, 2),

            "sway_score": round(self.sway_score, 2),

            "eyes_closed_frames": self.eyes_closed_frames,

            # Always True from the laptop – the Pi reads the real
            # FSR value in guardian_dart.py and acts on it there.
            "hands_on_wheel": True,

            "timestamp": time.time(),
        })

    # =====================================================
    # Main Loop
    # =====================================================

    def run(self):

        try:

            while True:

                ret, frame = self.cap.read()

                if not ret:
                    logger.error("Camera frame failed")
                    break

                frame = cv2.flip(frame, 1)

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                results = self.face_mesh.process(rgb)

                candidate_state = "NORMAL"

                self.face_detected = False

                if results.multi_face_landmarks:

                    self.face_detected = True

                    face_landmarks = results.multi_face_landmarks[0]

                    h, w, _ = frame.shape

                    landmarks = []

                    for lm in face_landmarks.landmark:

                        x = int(lm.x * w)
                        y = int(lm.y * h)

                        landmarks.append((x, y))

                    landmarks = np.array(landmarks)

                    # =================================================
                    # EYES
                    # =================================================

                    left_eye = landmarks[LEFT_EYE]
                    right_eye = landmarks[RIGHT_EYE]

                    left_ear = self.eye_aspect_ratio(left_eye)
                    right_ear = self.eye_aspect_ratio(right_eye)

                    ear = (left_ear + right_ear) / 2.0

                    # -------------------------------------------------
                    # DROWSINESS
                    # -------------------------------------------------

                    if ear < EAR_THRESHOLD:

                        self.eyes_closed_frames += 1

                    else:

                        self.eyes_closed_frames = 0

                    if self.eyes_closed_frames > DROWSY_FRAME_LIMIT:

                        candidate_state = "DROWSY"

                    # =================================================
                    # HEAD DIRECTION
                    # =================================================

                    nose = landmarks[1]

                    left_face = landmarks[234]
                    right_face = landmarks[454]

                    face_center_x = (
                        left_face[0] + right_face[0]
                    ) / 2

                    nose_offset = nose[0] - face_center_x

                    # -------------------------------------------------
                    # DISTRACTED
                    # -------------------------------------------------

                    if abs(nose_offset) > DISTRACTION_ANGLE:

                        candidate_state = "DISTRACTED"

                    # =================================================
                    # DIZZINESS
                    # =================================================

                    if self.last_nose is not None:

                        movement = np.linalg.norm(
                            nose - self.last_nose
                        )

                        self.movement_history.append(movement)

                        self.avg_movement = np.mean(
                            self.movement_history
                        )

                        self.sway_score = (
                            np.mean(self.movement_history)
                            +
                            np.std(self.movement_history)
                        )

                        if (
                            self.sway_score >
                            DIZZY_SWAY_THRESHOLD
                        ):
                            candidate_state = "DIZZY"

                    self.last_nose = nose

                    # =================================================
                    # Eye Count
                    # =================================================

                    self.eye_count = 0

                    if left_ear > EAR_THRESHOLD:
                        self.eye_count += 1

                    if right_ear > EAR_THRESHOLD:
                        self.eye_count += 1

                    # =================================================
                    # Draw landmarks
                    # =================================================

                    for point in left_eye:
                        cv2.circle(
                            frame,
                            tuple(point),
                            2,
                            (255, 255, 0),
                            -1,
                        )

                    for point in right_eye:
                        cv2.circle(
                            frame,
                            tuple(point),
                            2,
                            (255, 255, 0),
                            -1,
                        )

                else:

                    self.eye_count = 0

                    self.avg_movement = 0

                    self.sway_score = 0

                    self.last_nose = None

                # =====================================================
                # APPLY STATE
                # =====================================================

                self.set_state(candidate_state)

                # =====================================================
                # EMOTION
                # =====================================================

                self.emotion = self.detect_emotion()

                # =====================================================
                # DRAW UI
                # =====================================================

                state_color = {

                    "NORMAL": (0, 255, 0),

                    "DISTRACTED": (0, 165, 255),

                    "DIZZY": (0, 255, 255),

                    "DROWSY": (0, 0, 255),

                }.get(self.driver_state, (255, 255, 255))

                self.draw_text(
                    frame,
                    f"STATE: {self.driver_state}",
                    40,
                    state_color,
                )

                self.draw_text(
                    frame,
                    f"EMOTION: {self.emotion}",
                    80,
                    (255, 255, 255),
                )

                self.draw_text(
                    frame,
                    f"EAR: {ear:.2f}" if self.face_detected else "EAR: N/A",
                    120,
                    (255, 255, 0),
                )

                self.draw_text(
                    frame,
                    f"SWAY SCORE: {self.sway_score:.2f}",
                    160,
                    (255, 255, 0),
                )

                self.draw_text(
                    frame,
                    f"EYES CLOSED: {self.eyes_closed_frames}",
                    200,
                    (255, 255, 0),
                )

                self.draw_text(
                    frame,
                    "HANDS: Pi FSR sensor",
                    240,
                    (200, 200, 200),
                )

                # =====================================================
                # CLOUD
                # =====================================================

                self.sync_to_cloud()

                # =====================================================
                # SHOW
                # =====================================================

                cv2.namedWindow("ADAMS SYSTEM", cv2.WINDOW_NORMAL)
                cv2.resizeWindow("ADAMS SYSTEM", 720, 540)

                frame = cv2.resize(frame, (720, 540))

                cv2.imshow("ADAMS SYSTEM", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        finally:

            logger.info("Stopping ADAMS")

            self.cloud.stop()

            self.cap.release()

            cv2.destroyAllWindows()


# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":

    system = AdamsVisionSystem()

    system.run()