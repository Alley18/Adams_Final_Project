"""
cloud_sync.py – improved version

Changes vs original:
- Only pushes to Firebase when data actually changed (saves Pi CPU & bandwidth).
- Exponential back-off on repeated Firebase errors (max 30 s).
- Thread-safe data update with a lock.
- Graceful handling when firebase_admin is not installed.
"""

import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("ADAMS")

BASE_DIR = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH = Path(
    os.getenv("ADAMS_FIREBASE_SERVICE_ACCOUNT", BASE_DIR / "serviceAccountKey.json")
)
DATABASE_URL = os.getenv(
    "ADAMS_FIREBASE_DATABASE_URL",
    "https://adams-project-final-default-rtdb.asia-southeast1.firebasedatabase.app/",
)
DRIVER_STATUS_PATH = os.getenv("ADAMS_DRIVER_STATUS_PATH", "/driver_status")
SYNC_INTERVAL_SECONDS = 2
MAX_BACKOFF_SECONDS = 30

if not isinstance(DATABASE_URL, str) or not DATABASE_URL.strip():
    raise ValueError("ADAMS_FIREBASE_DATABASE_URL must be a non-empty string")


class CloudSync:

    def __init__(self):
        self._latest_data: dict = {}
        self._last_pushed: dict = {}          # track what we last sent
        self._lock = threading.Lock()
        self.firebase_enabled = False
        self.ref = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._backoff = SYNC_INTERVAL_SECONDS

        try:
            import firebase_admin
            from firebase_admin import credentials, db

            if not SERVICE_ACCOUNT_PATH.exists():
                raise FileNotFoundError(f"Missing {SERVICE_ACCOUNT_PATH}")

            if not firebase_admin._apps:
                cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
                firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

            self.ref = db.reference(DRIVER_STATUS_PATH)
            self.firebase_enabled = True
            logger.info("Firebase connected")

        except ImportError:
            logger.warning("firebase_admin not installed – cloud sync disabled")
        except Exception as e:
            logger.error(f"Firebase connection failed: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_data(self, data: dict) -> None:
        """Thread-safe data update called from the vision loop."""
        with self._lock:
            self._latest_data = data

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=MAX_BACKOFF_SECONDS)

    # ------------------------------------------------------------------
    # Internal sync loop
    # ------------------------------------------------------------------

    def _sync_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    data = dict(self._latest_data)

                # Only push when something actually changed
                if self.firebase_enabled and data and data != self._last_pushed:
                    self.ref.update(data)
                    self._last_pushed = dict(data)
                    self._backoff = SYNC_INTERVAL_SECONDS   # reset on success
                    logger.debug("Firebase synced")

            except Exception as e:
                logger.error(f"Firebase sync failed: {e}")
                # Exponential back-off so a flaky connection doesn't spam logs
                self._backoff = min(self._backoff * 2, MAX_BACKOFF_SECONDS)
                logger.info(f"Retrying in {self._backoff}s")

            self._stop_event.wait(self._backoff)
