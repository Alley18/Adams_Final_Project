# trip_logger.py – ADAMS v3
# Polls Firebase every 60 s and appends one CSV row per reading.
# Tracks emotion, driver state, and destination for each trip.
# Run alongside guardian_dart.py:  python trip_logger.py

import csv
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv(
    "ADAMS_FIREBASE_DATABASE_URL",
    "https://adams-project-final-default-rtdb.asia-southeast1.firebasedatabase.app/",
)

POLL_INTERVAL_SECONDS = 60       # one row per minute

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TRIP_LOGGER] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trip_logger.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("TRIP_LOGGER")

# ─────────────────────────────────────────────────────────────
# CSV schema
# ─────────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "timestamp_iso",       # human-readable UTC time
    "timestamp_epoch",     # raw epoch (for sorting / graphing)
    "trip_id",             # YYYYMMDD_HHMMSS of trip start
    "destination",         # last known destination name from Firebase
    "driver_state",        # NORMAL / DROWSY / DIZZY / DISTRACTED
    "emotion",             # raw per-frame emotion
    "dominant_emotion",    # stable committed emotion
    "hands_on_wheel",      # boolean from Pi FSR
    "eye_count",           # 0 / 1 / 2
    "eyes_closed_frames",  # int
    "avg_movement",        # float
    "sway_score",          # float
    "face_detected",       # boolean
]


def _csv_path(trip_id: str) -> Path:
    """One CSV file per trip, named by trip start time."""
    return LOG_DIR / f"trip_{trip_id}.csv"


def _append_row(path: Path, row: dict) -> None:
    """Append a single dict row to the CSV, writing header if new file."""
    file_exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ─────────────────────────────────────────────────────────────
# Trip tracker
# ─────────────────────────────────────────────────────────────

class TripLogger:

    def __init__(self):
        self._trip_id   = None
        self._csv_path  = None
        self._db        = None
        self._connect_firebase()

    def _connect_firebase(self) -> None:
        try:
            import firebase_admin
            from firebase_admin import credentials, db

            key_path = BASE_DIR / "serviceAccountKey.json"
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(key_path))
                firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

            self._driver_ref      = db.reference("/driver_status")
            self._destination_ref = db.reference("/adams")   # Flutter writes destination here
            logger.info("Firebase connected")

        except Exception as exc:
            logger.error(f"Firebase connection failed: {exc}")
            self._driver_ref      = None
            self._destination_ref = None

    def _start_trip(self) -> None:
        """Called when we first detect a non-NORMAL state or a destination set."""
        self._trip_id  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._csv_path = _csv_path(self._trip_id)
        logger.info(f"New trip started → {self._csv_path.name}")

    def _fetch_data(self) -> dict:
        """Pull latest values from Firebase."""
        try:
            driver_data = self._driver_ref.get() or {}
            adams_data  = self._destination_ref.get() or {}

            return {
                "driver_state":        driver_data.get("driver_state", "NORMAL"),
                "emotion":             driver_data.get("emotion", "NEUTRAL"),
                "dominant_emotion":    driver_data.get("dominant_emotion", "NEUTRAL"),
                "hands_on_wheel":      driver_data.get("hands_on_wheel", True),
                "eye_count":           driver_data.get("eye_count", 2),
                "eyes_closed_frames":  driver_data.get("eyes_closed_frames", 0),
                "avg_movement":        driver_data.get("avg_movement", 0.0),
                "sway_score":          driver_data.get("sway_score", 0.0),
                "face_detected":       driver_data.get("face_detected", False),
                # destination comes from the Flutter app writing to /adams
                "destination":         adams_data.get("destination_name", ""),
            }
        except Exception as exc:
            logger.error(f"Fetch error: {exc}")
            return {}

    def run(self) -> None:
        if self._driver_ref is None:
            logger.error("Firebase not connected — exiting.")
            return

        logger.info(f"Polling every {POLL_INTERVAL_SECONDS}s")

        while True:
            try:
                data = self._fetch_data()
                if not data:
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # Start a new trip if destination is set and we have none open
                destination = data.get("destination", "")
                if destination and self._trip_id is None:
                    self._start_trip()

                # If a trip is open, log the row
                if self._trip_id is not None:
                    now = datetime.now(timezone.utc)
                    row = {
                        "timestamp_iso":      now.isoformat(),
                        "timestamp_epoch":    now.timestamp(),
                        "trip_id":            self._trip_id,
                        "destination":        destination,
                        "driver_state":       data["driver_state"],
                        "emotion":            data["emotion"],
                        "dominant_emotion":   data["dominant_emotion"],
                        "hands_on_wheel":     data["hands_on_wheel"],
                        "eye_count":          data["eye_count"],
                        "eyes_closed_frames": data["eyes_closed_frames"],
                        "avg_movement":       round(data["avg_movement"], 3),
                        "sway_score":         round(data["sway_score"], 3),
                        "face_detected":      data["face_detected"],
                    }
                    _append_row(self._csv_path, row)
                    logger.info(
                        f"[{self._trip_id}] {data['driver_state']} | "
                        f"emotion={data['emotion']} | "
                        f"dominant={data['dominant_emotion']} | "
                        f"dest={destination or '—'}"
                    )

                    # Close the trip if destination is cleared
                    if not destination:
                        logger.info(f"Trip ended → {self._csv_path.name}")
                        self._trip_id  = None
                        self._csv_path = None

            except KeyboardInterrupt:
                logger.info("TripLogger stopped.")
                break
            except Exception as exc:
                logger.error(f"Loop error: {exc}")

            time.sleep(POLL_INTERVAL_SECONDS)


# ─────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    TripLogger().run()