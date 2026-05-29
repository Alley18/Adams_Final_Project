"""
ADAMS Eye Detector
==================
Wraps MediaPipe's Face Landmarker Tasks API to compute per-frame Eye Aspect
Ratio (EAR) values, detect sustained drowsiness, and identify driver
distraction via head-pose yaw estimation.

Authors : ADAMS Team
Version : 2.1.1
"""

import logging
import math
import os
import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ---------------------------------------------------------------------------
# Logging & Environment Setup
# ---------------------------------------------------------------------------
# Silence internal TensorFlow/oneDNN noise
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

logger = logging.getLogger("adams.eye_detector")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EAR_THRESHOLD: float = 0.25 
CLOSED_FRAMES_THRESHOLD: int = 10 
EAR_NORMALISER: float = 0.35 
YAW_THRESHOLD_DEG: float = 20.0
DISTRACTED_FRAMES_THRESHOLD: int = 8 

# MediaPipe Face Mesh landmark indices for EAR
LEFT_EYE_INDICES:  tuple[int, ...] = (362, 385, 387, 263, 373, 380)
RIGHT_EYE_INDICES: tuple[int, ...] = (33,  160, 158, 133, 153, 144)

# HUD colours
_GREEN  = (0, 255, 0)
_YELLOW = (0, 200, 255)
_RED    = (0, 0, 255)
_BLACK  = (0, 0, 0)

class EyeDetector:
    def __init__(
        self,
        model_path: str | None = None,
        ear_threshold: float = EAR_THRESHOLD,
        closed_frames_threshold: int = CLOSED_FRAMES_THRESHOLD,
        yaw_threshold_deg: float = YAW_THRESHOLD_DEG,
        distracted_frames_threshold: int = DISTRACTED_FRAMES_THRESHOLD,
    ) -> None:
        if model_path is None:
            model_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "face_landmarker.task",
            )

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found at '{model_path}'. Check filename!")

        self.ear_threshold = 0.15
        self.closed_frames_threshold = closed_frames_threshold
        self.yaw_threshold_deg = yaw_threshold_deg
        self.distracted_frames_threshold = distracted_frames_threshold

        self._closed_frame_count: int = 0
        self._distracted_frame_count: int = 0

        # Configure MediaPipe
        base_opts = python.BaseOptions(model_asset_path=model_path)
        opts = vision.FaceLandmarkerOptions(
            base_options=base_opts,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            num_faces=1,
        )
        self._detector = vision.FaceLandmarker.create_from_options(opts)

    def analyze(self, frame: np.ndarray) -> dict:
        rgb = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        result = self._detector.detect(rgb)

        if not result.face_landmarks:
            self._closed_frame_count = 0
            self._distracted_frame_count = 0
            return {
                "eye_opening": 1.0, "is_drowsy": False, "is_distracted": False,
                "yaw_deg": 0.0, "ear_value": 0.30, "face_detected": False,
            }

        landmarks = result.face_landmarks[0]

        # --- EAR / drowsiness ---
        left_ear  = self._compute_ear(landmarks, LEFT_EYE_INDICES)
        right_ear = self._compute_ear(landmarks, RIGHT_EYE_INDICES)
        avg_ear   = (left_ear + right_ear) / 2.0

        if avg_ear < self.ear_threshold:
            self._closed_frame_count += 1
        else:
            self._closed_frame_count = 0

        is_drowsy = self._closed_frame_count >= self.closed_frames_threshold
        eye_opening = round(min(avg_ear / EAR_NORMALISER, 1.0), 2)

        # --- Head-pose yaw ---
        yaw_deg = 0.0
        if result.facial_transformation_matrixes:
            yaw_deg = self._extract_yaw_deg(result.facial_transformation_matrixes[0])

        if abs(yaw_deg) > self.yaw_threshold_deg:
            self._distracted_frame_count += 1
        else:
            self._distracted_frame_count = 0

        is_distracted = self._distracted_frame_count >= self.distracted_frames_threshold

        return {
            "eye_opening": eye_opening,
            "is_drowsy": is_drowsy,
            "is_distracted": is_distracted,
            "yaw_deg": round(yaw_deg, 1),
            "ear_value": round(avg_ear, 3),
            "face_detected": True,
        }

    def draw_overlay(self, frame: np.ndarray, eye_data: dict) -> np.ndarray:
        frame = frame.copy()
        h, w = frame.shape[:2]
        is_drowsy = eye_data["is_drowsy"]
        is_distracted = eye_data.get("is_distracted", False)
        accent = _RED if is_drowsy else (_YELLOW if is_distracted else _GREEN)

        # Header
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 50), _BLACK, -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        cv2.putText(frame, "ADAMS SYSTEM: ACTIVE", (15, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, _GREEN, 1, cv2.LINE_AA)

        # Metrics
        cv2.putText(frame, f"EAR: {eye_data['ear_value']:.2f}", (20, 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, accent, 2, cv2.LINE_AA)
        cv2.putText(frame, f"Yaw: {eye_data['yaw_deg']:+.1f} deg", (20, 125), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, accent, 2, cv2.LINE_AA)

        # Alerts
        if is_drowsy:
            cv2.rectangle(frame, (0, 0), (w, h), _RED, 10)
            cv2.putText(frame, "DROWSINESS ALERT", (w // 2 - 140, h // 2), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, _RED, 3, cv2.LINE_AA)
        elif is_distracted:
            cv2.rectangle(frame, (0, 0), (w, h), _YELLOW, 10)
            cv2.putText(frame, "DISTRACTION ALERT", (w // 2 - 145, h // 2), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, _YELLOW, 3, cv2.LINE_AA)

        return frame

    @staticmethod
    def _compute_ear(landmarks, indices: tuple[int, ...]) -> float:
        pts = np.array([(landmarks[i].x, landmarks[i].y) for i in indices])
        vert_a = np.linalg.norm(pts[1] - pts[5])
        vert_b = np.linalg.norm(pts[2] - pts[4])
        horiz  = np.linalg.norm(pts[0] - pts[3])
        return float((vert_a + vert_b) / (2.0 * horiz)) if horiz > 0 else 0.0

    def _extract_yaw_deg(self, matrix_obj):
        try:
            m = np.array(matrix_obj.data).reshape(4, 4)
            yaw_rad = math.atan2(m[0, 2], m[2, 2])
            return float(math.degrees(yaw_rad))
        except:
            return 0.0

# ---------------------------------------------------------------------------
# Execution Block (Allows running this file directly)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        detector = EyeDetector()
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) # Fixed for Windows
        
        print("ADAMS Vision Online. Press 'q' to quit.")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            data = detector.analyze(frame)
            output = detector.draw_overlay(frame, data)

            cv2.imshow("ADAMS Face Mesh", output)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
            
        cap.release()
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"Error: {e}")