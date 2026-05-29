"""
ADAMS Stream Integration
========================
Bridge module that ships driver telemetry from the vision node to the
ADAMS backend REST API.  Designed to be replaced by live data from
``vision_node.py`` once the vision subsystem is integrated.

Authors : ADAMS Team
Version : 2.0.0
"""

import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from requests.exceptions import RequestException

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("adams.stream")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_URL: str = "http://127.0.0.1:8000/driver-status"
REQUEST_TIMEOUT: float = 5.0       # seconds before giving up on the backend
EYE_CLOSED_THRESHOLD: float = 0.20  # eye_opening below this → "closed"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class DriverTelemetry:
    """
    Raw sensor snapshot produced by the vision node.

    Attributes
    ----------
    eye_opening : float
        Normalised eye-opening ratio in [0.0, 1.0].
        0.0 = fully closed, 1.0 = fully open.
    is_yawning : bool
        Whether a yawn was detected in this frame.
    emotion : str
        Driver's detected emotional state (e.g., "Neutral", "Tired").
    gaze : str
        Estimated gaze direction (e.g., "Forward", "Left").
    confidence : float
        Emotion-classifier confidence in [0.0, 100.0].
    """
    eye_opening: float
    is_yawning: bool
    emotion: str
    gaze: str
    confidence: float


@dataclass
class BackendPayload:
    """
    Payload sent to the backend API endpoint.
    """
    eye_status: str        # "open" | "closed"
    emotion: str
    confidence: float
    timestamp: float


# ---------------------------------------------------------------------------
# Telemetry source (stub — replace with real vision_node output)
# ---------------------------------------------------------------------------
def get_live_telemetry() -> DriverTelemetry:
    """
    Return a live telemetry snapshot from the vision subsystem.

    .. note::
        This stub returns hard-coded values for testing.  In production,
        call ``vision_node.latest_frame_data()`` (or equivalent) here.
    """
    return DriverTelemetry(
        eye_opening=0.05,   # 5 % — very drowsy
        is_yawning=True,
        emotion="Tired",
        gaze="Forward",
        confidence=92.0,
    )


# ---------------------------------------------------------------------------
# Backend communication
# ---------------------------------------------------------------------------
def _build_payload(telemetry: DriverTelemetry) -> BackendPayload:
    """Derive a backend-ready payload from raw telemetry."""
    eye_status = "closed" if telemetry.eye_opening < EYE_CLOSED_THRESHOLD else "open"
    return BackendPayload(
        eye_status=eye_status,
        emotion=telemetry.emotion,
        confidence=telemetry.confidence,
        timestamp=time.time(),
    )


def send_status(telemetry: DriverTelemetry) -> Optional[int]:
    """
    Ship a telemetry snapshot to the ADAMS backend.

    Parameters
    ----------
    telemetry : DriverTelemetry
        Raw sensor data from the vision node.

    Returns
    -------
    int or None
        HTTP status code on success, or ``None`` if the backend is
        unreachable.
    """
    payload = _build_payload(telemetry)
    logger.debug("Sending payload: %s", payload)

    try:
        response = requests.post(
            BACKEND_URL,
            json=asdict(payload),
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info(
            "✅ Pushed — emotion=%s eye=%s  →  HTTP %d",
            payload.emotion,
            payload.eye_status,
            response.status_code,
        )
        return response.status_code

    except RequestException as exc:
        logger.warning("Backend unreachable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Entry point (smoke test)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("--- ADAMS Stream Integration Test ---")
    telemetry = get_live_telemetry()
    logger.info("Telemetry snapshot: %s", telemetry)
    status = send_status(telemetry)
    if status is None:
        logger.warning("No response from backend — is the server running?")