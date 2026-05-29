"""
guardian_dart.py – Remote Guardian Monitor

Reads live driver status data written by ADAMS to Firebase
(/driver_status) and acts as a secondary safety layer.

Responsibilities:
  - Streams real-time updates from Firebase
  - Logs every driver state transition
  - Escalates dangerous states after thresholds
  - Sends notifications (stub)
  - Writes alerts back to Firebase
  - Falls back to polling if streaming fails
  - Shows HELP on LCD when hands leave wheel during danger state

Usage:
    python guardian_dart.py

Requirements:
    pip install firebase-admin requests smbus2

Place:
    serviceAccountKey.json

in the same directory as this file.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from hardware import HardwareController

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

SERVICE_ACCOUNT_PATH = Path(
    os.getenv("ADAMS_FIREBASE_SERVICE_ACCOUNT", BASE_DIR / "serviceAccountKey.json")
)

DATABASE_URL = os.getenv(
    "ADAMS_FIREBASE_DATABASE_URL",
    "https://adams-project-final-default-rtdb.asia-southeast1.firebasedatabase.app/",
)
DRIVER_STATUS_PATH = os.getenv("ADAMS_DRIVER_STATUS_PATH", "/driver_status")

# Danger escalation thresholds (seconds)
ESCALATION_THRESHOLD_SECONDS = {
    "DISTRACTED": 8.0,
    "DIZZY":      6.0,
    "DROWSY":     10.0,
}

DANGER_STATES = {
    "DISTRACTED",
    "DIZZY",
    "DROWSY",
}

# How long hands must be off wheel (during danger) before HELP is shown
HANDS_OFF_HELP_THRESHOLD_SECONDS = 3.0

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GUARDIAN] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "guardian_dart.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("GUARDIAN_DART")

# ─────────────────────────────────────────────────────────────
# Notification Stub
# ─────────────────────────────────────────────────────────────


def send_notification(state: str, duration: float, data: dict) -> None:
    """
    Replace with actual SMS/email/Telegram notification logic.
    """
    logger.warning(
        f"[NOTIFY] Driver in {state} for {duration:.1f}s | "
        f"emotion={data.get('emotion')} | "
        f"hands_on_wheel={data.get('hands_on_wheel')} | "
        f"movement={data.get('avg_movement')}"
    )

    # Example Twilio implementation:
    #
    # from twilio.rest import Client
    # client = Client(TWILIO_SID, TWILIO_TOKEN)
    # client.messages.create(
    #     body=f"ADAMS ALERT: Driver {state} for {duration:.0f}s",
    #     from_=TWILIO_FROM,
    #     to=GUARDIAN_PHONE
    # )


# ─────────────────────────────────────────────────────────────
# Guardian System
# ─────────────────────────────────────────────────────────────


class GuardianDart:

    def __init__(self):

        self.firebase_enabled = False
        self.driver_ref  = None
        self.alert_ref   = None
        self._listener   = None

        self._current_state = "NORMAL"
        self._state_since   = None
        self._last_data     = {}
        self._escalated     = False

        # ── Hands-off tracking ───────────────────────────
        # Tracks when hands first left the wheel during a danger state
        self._hands_off_since  = None
        # Prevents showing HELP repeatedly until hands return
        self._help_displayed   = False

        self._lock = threading.Lock()

        self.hardware = HardwareController()

        self._connect_firebase()

    # ─────────────────────────────────────────────────────

    def _internet_available(self) -> bool:
        try:
            requests.get("https://google.com", timeout=3)
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────

    def _connect_firebase(self) -> None:
        try:
            import firebase_admin
            from firebase_admin import credentials, db

            if not SERVICE_ACCOUNT_PATH.exists():
                raise FileNotFoundError(
                    f"Missing Firebase key: {SERVICE_ACCOUNT_PATH}"
                )

            if not firebase_admin._apps:
                cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
                firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})

            self.driver_ref = db.reference(DRIVER_STATUS_PATH)
            self.alert_ref  = db.reference("/guardian_alerts")
            self.firebase_enabled = True
            logger.info("Connected to Firebase Realtime Database")

        except ImportError:
            logger.error(
                "firebase_admin not installed.\n"
                "Run: pip install firebase-admin"
            )
        except Exception as exc:
            logger.error(f"Firebase connection failed: {exc}")

    # ─────────────────────────────────────────────────────

    def _on_data_change(self, event) -> None:
        """Firebase realtime streaming callback."""
        try:
            if event.data is None:
                return

            with self._lock:
                if event.path == "/":
                    if not isinstance(event.data, dict):
                        return
                    self._last_data = event.data.copy()
                else:
                    key = event.path.lstrip("/")
                    self._last_data[key] = event.data
                data = self._last_data.copy()

            state   = data.get("driver_state", "NORMAL")
            emotion = data.get("emotion", "UNKNOWN")

            # Always read FSR directly from the Pi hardware.
            # Do NOT use data.get("hands_on_wheel") — that value
            # is written by the laptop which has no GPIO and
            # always sends True.
            hands = self.hardware.is_hands_on_wheel()

            self._handle_state(state, emotion, hands, data)

        except Exception as exc:
            logger.error(f"Stream callback error: {exc}")

    # ─────────────────────────────────────────────────────

    def _handle_state(
        self,
        state: str,
        emotion: str,
        hands: bool,
        data: dict,
    ) -> None:

        now = time.time()

        # Update Firebase with REAL Pi FSR value
        try:
            if self.driver_ref:
                self.driver_ref.update({
                    "hands_on_wheel": hands
                })
        except Exception as exc:
            logger.error(f"Failed updating hands_on_wheel: {exc}")

        # ── State transition ──────────────────────────────

        if state != self._current_state:

            logger.info(
                f"State change: {self._current_state} → {state} | "
                f"emotion={emotion} | "
                f"hands={'ON' if hands else 'OFF'}"
            )

            self._current_state = state
            self._escalated     = False

            # Reset hands-off tracking on every state change
            self._hands_off_since = None
            self._help_displayed  = False

            if state in DANGER_STATES:
                self._state_since = now
                logger.warning(f"⚠ DANGER state entered: {state}")
                self.hardware.buzz_alert(state)
                self.hardware.show_status_on_display(state)
            else:
                self._state_since = None
                # Clear display when driver returns to normal
                self.hardware.clear_display()

        # ── Escalation logic ─────────────────────────────

        if (
            state in DANGER_STATES
            and self._state_since is not None
            and not self._escalated
        ):
            duration  = now - self._state_since
            threshold = ESCALATION_THRESHOLD_SECONDS.get(state, 8.0)

            if duration >= threshold:
                logger.critical(
                    f"🚨 ESCALATION: {state} for {duration:.1f}s | "
                    f"emotion={emotion} | "
                    f"hands={'ON' if hands else 'OFF'}"
                )
                send_notification(state, duration, data)
                self._write_alert_to_firebase(state, duration, data)
                self._escalated = True

        # ── Hands-off wheel → HELP display ───────────────

        if state in DANGER_STATES:

            if not hands:

                if self._hands_off_since is None:
                    self._hands_off_since = now
                    logger.warning(f"🤚 Hands OFF wheel during {state} – starting timer")

                hands_off_duration = now - self._hands_off_since

                if (
                    hands_off_duration >= HANDS_OFF_HELP_THRESHOLD_SECONDS
                    and not self._help_displayed
                ):
                    logger.critical(
                        f"🆘 Hands off wheel for {hands_off_duration:.1f}s "
                        f"during {state} – possible medical emergency!"
                    )

                    print("\n" + "=" * 50)
                    print("  🆘  EMERGENCY DETECTED  🆘")
                    print(f"  STATE   : {state}")
                    print(f"  HANDS   : OFF WHEEL for {hands_off_duration:.1f}s")
                    print(f"  EMOTION : {data.get('emotion', 'UNKNOWN')}")
                    print("  ACTION  : HELP displayed on LCD")
                    print("  -> Firebase alert written")
                    print("=" * 50 + "\n")

                    self.hardware.buzz_alert("EMERGENCY")

                    self.hardware.show_help_on_display()
                    self._write_alert_to_firebase(
                        state="HANDS_OFF_EMERGENCY",
                        duration=hands_off_duration,
                        data=data,
                    )
                    self._help_displayed = True

            else:
                # Hands returned to wheel – reset tracking and clear HELP
                if self._hands_off_since is not None:
                    logger.info("✅ Hands returned to wheel – clearing HELP display")
                    self._hands_off_since = None
                    self._help_displayed  = False
                    self.hardware.show_status_on_display(state)

        else:
            self._hands_off_since = None
            self._help_displayed  = False

    # ─────────────────────────────────────────────────────

    def _write_alert_to_firebase(
        self,
        state: str,
        duration: float,
        data: dict,
    ) -> None:

        if not self.firebase_enabled or self.alert_ref is None:
            return

        try:
            alert = {
                "state":              state,
                "duration_seconds":   round(duration, 1),
                "emotion":            data.get("emotion"),
                "hands_on_wheel":     data.get("hands_on_wheel"),
                "avg_movement":       data.get("avg_movement"),
                "eyes_closed_frames": data.get("eyes_closed_frames"),
                "timestamp_iso":      datetime.now(timezone.utc).isoformat(),
                "timestamp_epoch":    time.time(),
            }
            self.alert_ref.push(alert)
            logger.info("Alert written to Firebase /guardian_alerts")

        except Exception as exc:
            logger.error(f"Failed writing alert: {exc}")

    # ─────────────────────────────────────────────────────

    def _poll_loop(self, interval: float = 1.5) -> None:

        logger.info(f"Polling Firebase every {interval}s")

        while True:
            try:
                if not self._internet_available():
                    logger.warning("No internet connection...")
                    time.sleep(interval)
                    continue

                data = self.driver_ref.get()

                if isinstance(data, dict):
                    with self._lock:
                        self._last_data = data.copy()

                    state   = data.get("driver_state", "NORMAL")
                    emotion = data.get("emotion", "UNKNOWN")

                    # Read FSR directly from Pi hardware
                    hands = self.hardware.is_hands_on_wheel()

                    self._handle_state(state, emotion, hands, data)

            except Exception as exc:
                logger.error(f"Polling error: {exc}")

            time.sleep(interval)

    # ─────────────────────────────────────────────────────

    def run(self) -> None:

        if not self.firebase_enabled:
            logger.error("Firebase not connected.")
            return

        logger.info("GuardianDart listening for driver updates...")

        try:
            self._listener = self.driver_ref.listen(self._on_data_change)

            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("GuardianDart stopped by user.")

        except Exception as exc:
            logger.error(f"Streaming failed: {exc}")
            logger.warning("Falling back to polling mode...")
            self._poll_loop()

        finally:
            try:
                if self._listener:
                    self._listener.close()
            except Exception:
                pass

            self.hardware.cleanup()


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    guardian = GuardianDart()
    guardian.run()