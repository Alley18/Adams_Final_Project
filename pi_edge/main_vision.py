"""
main_vision.py – ADAMS v3
(Danger detection: scored DROWSY / DIZZY / DISTRACTED)
(Emotion engine: scored 6-state detection + rolling buffer)
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

CAMERA_INDEX = 0

# -------------------------------
# Drowsiness  (UNCHANGED)
# -------------------------------

EAR_THRESHOLD = 0.18
DROWSY_FRAME_LIMIT = 35
EAR_DROOPY_THRESHOLD = 0.23
DROWSY_SCORE_ACTIVATE = 75
DROWSY_LOST_FACE_HOLD_FRAMES = 45
EYES_MISSING_DROWSY_FRAMES = 10
FACE_MISSING_DROWSY_FRAMES = 18
HEAD_DOWN_RATIO_ACTIVATE = 0.42

# -------------------------------
# Distraction  (UNCHANGED)
# -------------------------------

DISTRACTION_ANGLE = 10
DISTRACTION_SCORE_ACTIVATE = 75

# -------------------------------
# Dizziness  (UNCHANGED)
# -------------------------------

MOVEMENT_HISTORY_SIZE = 20
DIZZY_SWAY_THRESHOLD = 6
DIZZY_SCORE_ACTIVATE = 75
HANDS_LOG_INTERVAL_SECONDS = 5
FSR_SAMPLE_INTERVAL_SECONDS = 0.5

# Prevent one noisy camera frame from flipping the state immediately.
DANGER_STATE_CONFIRM_FRAMES = 4
NORMAL_STATE_CONFIRM_FRAMES = 8

# -------------------------------
# Emotion buffer  (NEW)
# -------------------------------

EMOTION_BUFFER_SECONDS   = 60    # rolling window length
EMOTION_STABILITY_RATIO  = 0.80  # must be >80 % of buffer
EMOTION_COMMIT_COOLDOWN  = 600   # 10 min between reroutes (seconds)
EMOTION_CONFIRM_FRAMES   = 24    # prevents frame-to-frame raw emotion flips
EMOTION_SWITCH_MARGIN    = 18    # new emotion must beat current one by this much

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

LEFT_EYE  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


# =========================================================
# MAIN SYSTEM
# =========================================================

class AdamsVisionSystem:

    def __init__(self):

        logger.info("Starting ADAMS v3")

        self.hardware = HardwareController()

        self.hands_on_wheel = True
        self.fsr_sample = {
            "hands_on": True,
            "simulated": True,
            "active_count": 0,
            "threshold": 0,
            "reads": [],
        }
        self._last_fsr_read_time = 0.0

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
        # Danger state  (UNCHANGED)
        # -------------------------------

        self.driver_state    = "NORMAL"
        self._pending_state = "NORMAL"
        self._pending_state_frames = 0
        self.eyes_closed_frames = 0
        self.face_detected   = False
        self.eye_count       = 2
        self.face_missing_frames = 0
        self.eyes_missing_frames = 0
        self.avg_movement    = 0.0
        self.sway_score      = 0.0
        self.nose_offset     = 0.0
        self.head_down_ratio = 0.0
        self.last_nose       = None
        self.movement_history = deque(maxlen=MOVEMENT_HISTORY_SIZE)
        self.state_scores = {
            "NORMAL": 100,
            "DROWSY": 0,
            "DISTRACTED": 0,
            "DIZZY": 0,
        }
        self.state_confidence = 100
        self.state_reason = "Driver appears alert."
        self.candidate_state = "NORMAL"
        self.candidate_confidence = 100
        self.candidate_reason = "Driver appears alert."

        # -------------------------------
        # Emotion  (NEW — replaces single self.emotion)
        # -------------------------------

        self.emotion           = "NEUTRAL"     # current raw reading
        self.dominant_emotion  = "NEUTRAL"     # stable committed value → sent to cloud / app
        self.emotion_scores = {
            "NEUTRAL": 100,
            "FOCUSED": 0,
            "TIRED": 0,
            "STRESSED": 0,
            "RELAXED": 0,
            "HAPPY": 0,
        }
        self.emotion_confidence = 100
        self._pending_emotion = "NEUTRAL"
        self._pending_emotion_frames = 0

        # rolling buffer: list of (timestamp, emotion_string)
        self._emotion_buffer   = deque()
        self._last_commit_time = 0.0           # epoch of last dominant_emotion change

    # =====================================================
    # Utilities  (UNCHANGED)
    # =====================================================

    def eye_aspect_ratio(self, eye):
        vertical1  = np.linalg.norm(eye[1] - eye[5])
        vertical2  = np.linalg.norm(eye[2] - eye[4])
        horizontal = np.linalg.norm(eye[0] - eye[3])
        return (vertical1 + vertical2) / (2.0 * horizontal)

    def set_state(self, new_state):
        if new_state == self.driver_state:
            self._pending_state = new_state
            self._pending_state_frames = 0
            return

        if new_state != self._pending_state:
            self._pending_state = new_state
            self._pending_state_frames = 1
            return

        self._pending_state_frames += 1
        required_frames = (
            NORMAL_STATE_CONFIRM_FRAMES
            if new_state == "NORMAL"
            else DANGER_STATE_CONFIRM_FRAMES
        )

        if self._pending_state_frames >= required_frames:
            logger.warning(f"STATE: {self.driver_state} -> {new_state}")
            self.driver_state = new_state
            self._pending_state_frames = 0

    def draw_text(self, frame, text, y, color):
        cv2.putText(frame, text, (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    def draw_small_text(self, frame, text, y, color=(230, 230, 230)):
        cv2.putText(frame, text, (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)

    def draw_score_line(self, frame, label, value, y, color):
        x = 20
        width = 150
        cv2.putText(frame, f"{label}: {value:3d}%", (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 1)
        cv2.rectangle(frame, (x + 115, y - 12), (x + 115 + width, y - 3),
                      (55, 55, 55), -1)
        cv2.rectangle(frame, (x + 115, y - 12),
                      (x + 115 + int(width * value / 100), y - 3),
                      color, -1)

    def update_hands_on_wheel(self, now: float) -> None:
        if now - self._last_fsr_read_time < FSR_SAMPLE_INTERVAL_SECONDS:
            return

        self._last_fsr_read_time = now
        try:
            sample = self.hardware.read_logged_fsr_sample()
            self.fsr_sample = sample
            self.hands_on_wheel = bool(sample.get("hands_on", True))
        except Exception as exc:
            logger.error(f"FSR read failed: {exc}")
            self.fsr_sample = {
                "hands_on": self.hands_on_wheel,
                "error": str(exc),
                "simulated": True,
            }

    def draw_system_display(self, frame, ear: float) -> None:
        state_color = {
            "NORMAL":      (0, 255, 0),
            "DISTRACTED":  (0, 165, 255),
            "DIZZY":       (0, 255, 255),
            "DROWSY":      (0, 0, 255),
        }.get(self.driver_state, (255, 255, 255))

        overlay = frame.copy()
        cv2.rectangle(overlay, (8, 8), (520, 350), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        self.draw_text(
            frame,
            f"STATE: {self.driver_state} {self.state_confidence}%",
            40,
            state_color,
        )
        self.draw_small_text(
            frame,
            f"CANDIDATE: {self.candidate_state} {self.candidate_confidence}%",
            68,
            (220, 220, 220),
        )
        self.draw_small_text(
            frame,
            f"REASON: {self.candidate_reason[:58]}",
            92,
            (200, 220, 255),
        )

        self.draw_score_line(frame, "DROWSY", self.state_scores["DROWSY"], 124, (0, 0, 255))
        self.draw_score_line(frame, "DISTRACT", self.state_scores["DISTRACTED"], 148, (0, 165, 255))
        self.draw_score_line(frame, "DIZZY", self.state_scores["DIZZY"], 172, (0, 255, 255))
        self.draw_score_line(frame, "NORMAL", self.state_scores["NORMAL"], 196, (0, 255, 0))

        self.draw_small_text(
            frame,
            f"EMOTION: {self.emotion} {self.emotion_confidence}%  DOMINANT: {self.dominant_emotion}",
            226,
            (255, 255, 255),
        )
        self.draw_score_line(frame, "TIRED", self.emotion_scores["TIRED"], 252, (130, 160, 255))
        self.draw_score_line(frame, "STRESS", self.emotion_scores["STRESSED"], 276, (0, 180, 255))
        self.draw_score_line(frame, "FOCUS", self.emotion_scores["FOCUSED"], 300, (120, 255, 120))

        ear_text = f"{ear:.2f}" if self.face_detected else "N/A"
        self.draw_small_text(
            frame,
            (
                f"EAR {ear_text} | eyes {self.eye_count}/2 | missing "
                f"{self.eyes_missing_frames} | head_down {self.head_down_ratio:.2f}"
            ),
            330,
            (255, 255, 0),
        )

    @staticmethod
    def clamp_percent(value: float) -> int:
        return int(max(0, min(100, round(value))))

    def calculate_state_scores(self, ear: float) -> dict[str, int]:
        """
        Convert raw vision measurements into confidence scores.
        Drowsy is intentionally allowed to beat distracted because closed
        or hidden eyes are common when a driver is falling asleep.
        """
        drowsy_score = 0.0

        if self.face_detected:
            closed_frame_score = (
                self.eyes_closed_frames / max(1, DROWSY_FRAME_LIMIT)
            ) * 100

            ear_score = 0.0
            if ear <= EAR_THRESHOLD:
                ear_score = 45 + min(20, self.eyes_closed_frames * 2)
            elif ear < EAR_DROOPY_THRESHOLD:
                droopy_range = EAR_DROOPY_THRESHOLD - EAR_THRESHOLD
                ear_score = 30 + ((EAR_DROOPY_THRESHOLD - ear) / droopy_range) * 25

            eyes_missing_score = 0.0
            if self.eye_count == 0:
                eyes_missing_score = (
                    self.eyes_missing_frames / max(1, EYES_MISSING_DROWSY_FRAMES)
                ) * 90

            head_down_score = 0.0
            if self.head_down_ratio >= HEAD_DOWN_RATIO_ACTIVATE:
                head_down_score = 70 + (
                    (self.head_down_ratio - HEAD_DOWN_RATIO_ACTIVATE)
                    / max(0.01, 0.18)
                ) * 30
                if self.eye_count == 0:
                    head_down_score = max(head_down_score, 92)

            drowsy_score = max(
                closed_frame_score,
                ear_score,
                eyes_missing_score,
                head_down_score,
            )
        else:
            if (
                self.driver_state == "DROWSY"
                and self.face_missing_frames <= DROWSY_LOST_FACE_HOLD_FRAMES
            ):
                drowsy_score = 90 - min(25, self.face_missing_frames * 0.6)
            elif self.face_missing_frames >= FACE_MISSING_DROWSY_FRAMES:
                drowsy_score = 80
            elif self.eyes_closed_frames >= DROWSY_FRAME_LIMIT * 0.6:
                drowsy_score = 70 - min(30, self.face_missing_frames)

        distraction_score = 0.0
        drowsy_evidence_is_strong = (
            drowsy_score >= 60
            or self.eyes_closed_frames >= DROWSY_FRAME_LIMIT * 0.4
            or self.eyes_missing_frames >= EYES_MISSING_DROWSY_FRAMES
            or self.head_down_ratio >= HEAD_DOWN_RATIO_ACTIVATE
        )
        if self.face_detected and self.eye_count >= 1 and not drowsy_evidence_is_strong:
            angle = abs(self.nose_offset)
            if angle >= DISTRACTION_ANGLE:
                distraction_score = 65 + (
                    (angle - DISTRACTION_ANGLE) / max(1, DISTRACTION_ANGLE)
                ) * 35
            elif angle >= DISTRACTION_ANGLE * 0.7:
                distraction_score = 35 + (
                    (angle - (DISTRACTION_ANGLE * 0.7))
                    / max(1, DISTRACTION_ANGLE * 0.3)
                ) * 25

        dizzy_score = 0.0
        if self.sway_score >= DIZZY_SWAY_THRESHOLD:
            dizzy_score = 75 + (
                (self.sway_score - DIZZY_SWAY_THRESHOLD)
                / max(1, DIZZY_SWAY_THRESHOLD)
            ) * 25
        elif self.sway_score > DIZZY_SWAY_THRESHOLD * 0.55:
            dizzy_score = 35 + (
                (self.sway_score - DIZZY_SWAY_THRESHOLD * 0.55)
                / max(1, DIZZY_SWAY_THRESHOLD * 0.45)
            ) * 35

        top_danger_score = max(drowsy_score, distraction_score, dizzy_score)
        normal_score = max(0.0, 100 - top_danger_score)
        if self.face_detected and top_danger_score < 50:
            normal_score = max(normal_score, 75)
        if not self.face_detected:
            normal_score = min(normal_score, 45)

        self.state_scores = {
            "NORMAL": self.clamp_percent(normal_score),
            "DROWSY": self.clamp_percent(drowsy_score),
            "DISTRACTED": self.clamp_percent(distraction_score),
            "DIZZY": self.clamp_percent(dizzy_score),
        }
        return self.state_scores

    def choose_candidate_state(self, ear: float) -> str:
        scores = self.calculate_state_scores(ear)

        if scores["DROWSY"] >= DROWSY_SCORE_ACTIVATE:
            self.candidate_state = "DROWSY"
            self.candidate_confidence = scores["DROWSY"]
            if self.head_down_ratio >= HEAD_DOWN_RATIO_ACTIVATE and self.eye_count == 0:
                self.candidate_reason = "Head is down and eyes are not visible; assuming slept."
            elif self.eye_count == 0 or self.eyes_missing_frames >= EYES_MISSING_DROWSY_FRAMES:
                self.candidate_reason = "Eyes are not visible long enough; assuming drowsy/slept."
            elif not self.face_detected:
                self.candidate_reason = "Face/eyes missing for too long; assuming drowsy instead of distracted."
            else:
                self.candidate_reason = "Eyes are closed or heavy; drowsy has priority over distraction."
            return "DROWSY"

        if scores["DIZZY"] >= DIZZY_SCORE_ACTIVATE:
            self.candidate_state = "DIZZY"
            self.candidate_confidence = scores["DIZZY"]
            self.candidate_reason = "Head movement/sway is high."
            return "DIZZY"

        if scores["DISTRACTED"] >= DISTRACTION_SCORE_ACTIVATE:
            self.candidate_state = "DISTRACTED"
            self.candidate_confidence = scores["DISTRACTED"]
            self.candidate_reason = "Head is turned away while eyes are not showing drowsy evidence."
            return "DISTRACTED"

        self.candidate_state = "NORMAL"
        self.candidate_confidence = scores["NORMAL"]
        if not self.face_detected:
            self.candidate_reason = "Face or eyes are not visible; not treating this as distracted."
        else:
            self.candidate_reason = "Driver appears alert."
        return "NORMAL"

    def update_state_context(self) -> None:
        self.state_confidence = self.state_scores.get(self.driver_state, 0)
        if self.driver_state == self.candidate_state:
            self.state_reason = self.candidate_reason
            return

        self.state_reason = (
            f"Waiting for stable evidence before changing "
            f"from {self.driver_state} to {self.candidate_state}."
        )

    def calculate_emotion_scores(self, ear: float) -> dict[str, int]:
        tired_score = self.state_scores.get("DROWSY", 0)
        stressed_score = self.state_scores.get("DIZZY", 0)
        neutral_score = 45 if self.face_detected else 80
        focused_score = 0
        relaxed_score = 0
        happy_score = 0

        top_danger_score = max(
            self.state_scores.get("DROWSY", 0),
            self.state_scores.get("DISTRACTED", 0),
            self.state_scores.get("DIZZY", 0),
        )

        if self.face_detected and top_danger_score < 60:
            if self.eye_count >= 2:
                focused_score = 75 if ear <= 0.31 else 55
                happy_score = 65 if ear > 0.31 and self.sway_score < 2.5 else 0
                relaxed_score = 55 if ear >= 0.24 and self.sway_score < 3.0 else 35
            elif self.eye_count == 1:
                relaxed_score = 60

        if self.state_scores.get("DISTRACTED", 0) >= DISTRACTION_SCORE_ACTIVATE:
            neutral_score = max(neutral_score, 60)

        if tired_score >= 70:
            neutral_score = min(neutral_score, 35)
            focused_score = 0
            relaxed_score = 0
            happy_score = 0

        if stressed_score >= 70:
            neutral_score = min(neutral_score, 40)
            focused_score = 0
            relaxed_score = 0
            happy_score = 0

        self.emotion_scores = {
            "NEUTRAL": self.clamp_percent(neutral_score),
            "FOCUSED": self.clamp_percent(focused_score),
            "TIRED": self.clamp_percent(tired_score),
            "STRESSED": self.clamp_percent(stressed_score),
            "RELAXED": self.clamp_percent(relaxed_score),
            "HAPPY": self.clamp_percent(happy_score),
        }
        return self.emotion_scores

    def set_emotion(self, new_emotion: str) -> None:
        if new_emotion == self.emotion:
            self._pending_emotion = new_emotion
            self._pending_emotion_frames = 0
            return

        if new_emotion != self._pending_emotion:
            self._pending_emotion = new_emotion
            self._pending_emotion_frames = 1
            return

        self._pending_emotion_frames += 1
        required_frames = EMOTION_CONFIRM_FRAMES
        if new_emotion == "TIRED" and self.candidate_state == "DROWSY":
            required_frames = 3
        elif new_emotion == "STRESSED" and self.candidate_state == "DIZZY":
            required_frames = 5

        if self._pending_emotion_frames >= required_frames:
            self.emotion = new_emotion
            self._pending_emotion_frames = 0

    # =====================================================
    # Emotion engine  (EXPANDED — 6 states)
    # Maps from existing sensor data; no new libraries.
    # Danger evidence affects emotion scores (DROWSY -> TIRED,
    # DIZZY -> STRESSED). DISTRACTED is not treated as stress by itself.
    # Below that, EAR + sway give finer granularity.
    # =====================================================

    def detect_emotion(self, ear: float) -> str:
        """
        Returns one of: TIRED | STRESSED | RELAXED | HAPPY | FOCUSED | NEUTRAL

        Emotion is derived from scored evidence, not directly from the
        current state label. Looking away is a safety state, but it is
        not enough by itself to call the driver stressed.
        """
        scores = self.calculate_emotion_scores(ear)
        top_emotion, top_score = max(scores.items(), key=lambda item: item[1])
        self.emotion_confidence = top_score

        if top_score < 60:
            return "NEUTRAL"

        current_score = scores.get(self.emotion, 0)
        if (
            self.emotion != "NEUTRAL"
            and top_emotion != self.emotion
            and top_score < current_score + EMOTION_SWITCH_MARGIN
        ):
            self.emotion_confidence = current_score
            return self.emotion

        return top_emotion

    # =====================================================
    # Emotion buffer  (NEW)
    # Collects raw emotion readings every frame.
    # Every EMOTION_BUFFER_SECONDS it checks whether one
    # emotion appears >EMOTION_STABILITY_RATIO of the time.
    # If stable, commits dominant_emotion (with cooldown).
    # =====================================================

    def update_emotion_buffer(self, now: float):
        """
        Prune old entries, push current reading, then attempt
        to commit a new dominant_emotion if stable enough.
        """
        cutoff = now - EMOTION_BUFFER_SECONDS
        while self._emotion_buffer and self._emotion_buffer[0][0] < cutoff:
            self._emotion_buffer.popleft()

        self._emotion_buffer.append((now, self.emotion))

        total = len(self._emotion_buffer)
        if total < 10:          # not enough data yet
            return

        # Count occurrences
        counts: dict[str, int] = {}
        for _, e in self._emotion_buffer:
            counts[e] = counts.get(e, 0) + 1

        top_emotion, top_count = max(counts.items(), key=lambda x: x[1])
        ratio = top_count / total

        if ratio < EMOTION_STABILITY_RATIO:
            return              # too unstable — keep current dominant

        # Only commit if cooldown has elapsed
        if top_emotion == self.dominant_emotion:
            return              # already committed this emotion

        if (now - self._last_commit_time) < EMOTION_COMMIT_COOLDOWN:
            return              # cooldown not yet elapsed

        logger.info(
            f"DOMINANT EMOTION: {self.dominant_emotion} -> {top_emotion} "
            f"(stability {ratio:.0%}, {top_count}/{total} readings)"
        )
        self.dominant_emotion  = top_emotion
        self._last_commit_time = now

    # =====================================================
    # Firebase Sync  (updated to include dominant_emotion)
    # =====================================================

    def sync_to_cloud(self):
        self.cloud.update_data({
            "driver_state":      self.driver_state,
            "state_confidence":  self.state_confidence,
            "state_scores":      self.state_scores,
            "state_reason":      self.state_reason,
            "candidate_state":   self.candidate_state,
            "candidate_confidence": self.candidate_confidence,
            "candidate_reason":  self.candidate_reason,
            "emotion":           self.emotion,           # raw, every frame
            "emotion_confidence": self.emotion_confidence,
            "emotion_scores":    self.emotion_scores,
            "dominant_emotion":  self.dominant_emotion,  # stable, for rerouting
            "face_detected":     self.face_detected,
            "eye_count":         self.eye_count,
            "avg_movement":      round(self.avg_movement, 2),
            "sway_score":        round(self.sway_score, 2),
            "nose_offset":       round(self.nose_offset, 2),
            "head_down_ratio":   round(self.head_down_ratio, 3),
            "face_missing_frames": self.face_missing_frames,
            "eyes_missing_frames": self.eyes_missing_frames,
            "eyes_closed_frames": self.eyes_closed_frames,
            "hands_on_wheel":    self.hands_on_wheel,
            "timestamp":         time.time(),
        })

    # =====================================================
    # Main Loop  (danger detection section UNCHANGED)
    # =====================================================

    def run(self):

        try:

            while True:

                ret, frame = self.cap.read()

                if not ret:
                    logger.error("Camera frame failed")
                    break

                frame = cv2.flip(frame, 1)
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.face_mesh.process(rgb)

                self.face_detected = False
                ear = 0.0
                self.nose_offset = 0.0
                self.head_down_ratio = 0.0

                if results.multi_face_landmarks:

                    self.face_detected = True
                    self.face_missing_frames = 0
                    face_landmarks = results.multi_face_landmarks[0]
                    h, w, _ = frame.shape

                    landmarks = []
                    for lm in face_landmarks.landmark:
                        landmarks.append((int(lm.x * w), int(lm.y * h)))
                    landmarks = np.array(landmarks)

                    # ==============================================
                    # EYES  (UNCHANGED)
                    # ==============================================

                    left_eye  = landmarks[LEFT_EYE]
                    right_eye = landmarks[RIGHT_EYE]
                    left_ear  = self.eye_aspect_ratio(left_eye)
                    right_ear = self.eye_aspect_ratio(right_eye)
                    ear       = (left_ear + right_ear) / 2.0

                    # DROWSINESS  (UNCHANGED)
                    if ear < EAR_THRESHOLD:
                        self.eyes_closed_frames += 1
                    else:
                        self.eyes_closed_frames = 0

                    # HEAD DIRECTION  (UNCHANGED)
                    nose       = landmarks[1]
                    left_face  = landmarks[234]
                    right_face = landmarks[454]
                    face_center_x = (left_face[0] + right_face[0]) / 2
                    self.nose_offset = nose[0] - face_center_x

                    forehead = landmarks[10]
                    chin = landmarks[152]
                    eye_center_y = (
                        np.mean(left_eye[:, 1]) + np.mean(right_eye[:, 1])
                    ) / 2
                    face_height = max(1.0, float(abs(chin[1] - forehead[1])))
                    self.head_down_ratio = max(
                        0.0,
                        float(nose[1] - eye_center_y) / face_height,
                    )

                    # DIZZINESS  (UNCHANGED)
                    if self.last_nose is not None:
                        movement = np.linalg.norm(nose - self.last_nose)
                        self.movement_history.append(movement)
                        self.avg_movement = np.mean(self.movement_history)
                        self.sway_score   = (
                            np.mean(self.movement_history) +
                            np.std(self.movement_history)
                        )
                    self.last_nose = nose

                    # Eye count  (UNCHANGED)
                    self.eye_count = 0
                    if left_ear  > EAR_THRESHOLD: self.eye_count += 1
                    if right_ear > EAR_THRESHOLD: self.eye_count += 1
                    if self.eye_count == 0:
                        self.eyes_missing_frames += 1
                    else:
                        self.eyes_missing_frames = 0

                    # Draw landmarks  (UNCHANGED)
                    for point in left_eye:
                        cv2.circle(frame, tuple(point), 2, (255, 255, 0), -1)
                    for point in right_eye:
                        cv2.circle(frame, tuple(point), 2, (255, 255, 0), -1)

                else:
                    self.face_missing_frames += 1
                    self.eyes_missing_frames += 1
                    self.eye_count    = 0
                    self.avg_movement = 0
                    self.sway_score   = 0
                    self.last_nose    = None

                # ==============================================
                # APPLY DANGER STATE  (UNCHANGED)
                # ==============================================

                candidate_state = self.choose_candidate_state(ear)
                self.set_state(candidate_state)
                self.update_state_context()

                # ==============================================
                # EMOTION  (new 6-state engine + buffer)
                # ==============================================

                now          = time.time()
                self.set_emotion(self.detect_emotion(ear))
                self.update_emotion_buffer(now)

                # ==============================================
                # DRAW UI
                # ==============================================

                self.draw_system_display(frame, ear)

                # ==============================================
                # CLOUD
                # ==============================================

                self.update_hands_on_wheel(now)
                self.sync_to_cloud()

                # ==============================================
                # SHOW
                # ==============================================

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
