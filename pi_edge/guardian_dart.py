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
  - Shows HELP on LCD / matrix when hands leave wheel for 30s

FIX: Dedicated FSR push thread writes hands_on_wheel every 200ms
     independently of the main poll loop, so mobile sees near-instant
     on/off changes without waiting for the full poll cycle.

FIX: Live status thread writes full guardian_live node every second so
     mobile always has a real-time view of the current state + hands.

FIX: Internet check moved to its own background thread so it never
     blocks the FSR push loop or the poll loop (hardware always responds).

FIX: HANDS_OFF_HELP_THRESHOLD_SECONDS raised to 30.0 (was 3.0).

FIX: Hands-off timer no longer resets on state transitions (DIZZY →
     DISTRACTED → DIZZY was resetting the timer every ~2s, preventing
     HELP from ever triggering). The timer now only resets when the
     driver actually puts their hands back on the wheel.
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
DRIVER_STATUS_PATH  = os.getenv("ADAMS_DRIVER_STATUS_PATH", "/driver_status")
USE_FIREBASE_STREAM = os.getenv("ADAMS_FIREBASE_STREAM", "0") == "1"

# Danger escalation thresholds (seconds)
ESCALATION_THRESHOLD_SECONDS = {
    "DISTRACTED": 1.0,
    "DIZZY":      1.0,
    "DROWSY":     1.0,
}

DANGER_STATES = {
    "DISTRACTED",
    "DIZZY",
    "DROWSY",
}

# FIX: Raised from 3.0 to 30.0 — HELP should only trigger after the
# driver has had their hands off the wheel for a full 30 seconds.
HANDS_OFF_HELP_THRESHOLD_SECONDS = float(
    os.getenv("ADAMS_HANDS_OFF_HELP_THRESHOLD", "30.0")
)

# Thread intervals (tunable via env vars)
FSR_PUSH_INTERVAL       = float(os.getenv("ADAMS_FSR_PUSH_INTERVAL",   "0.2"))  # hands update
POLL_INTERVAL           = float(os.getenv("ADAMS_POLL_INTERVAL",        "0.3"))  # driver state
LIVE_STATUS_INTERVAL    = float(os.getenv("ADAMS_LIVE_STATUS_INTERVAL", "1.0"))  # live node
INTERNET_CHECK_INTERVAL = float(os.getenv("ADAMS_INTERNET_CHECK_INTERVAL", "1.0"))  # connectivity

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
        self.driver_ref = None
        self.alert_ref  = None
        self.live_ref   = None   # /guardian_live — updated every second
        self._listener  = None

        self._current_state = "NORMAL"
        self._state_since   = None
        self._last_data     = {}
        self._escalated     = False

        # Hands-off tracking
        # FIX: _hands_off_since is now ONLY reset when hands return to wheel.
        # Previously it was reset on every state transition, so rapid
        # DIZZY→DISTRACTED→DIZZY flips would restart the 30s timer each time
        # and HELP could never trigger.
        self._hands_off_since = None
        self._help_displayed  = False

        # Latest FSR reading shared between threads
        self._latest_hands_on = True
        self._fsr_lock = threading.Lock()

        # Internet flag updated by background thread
        self._internet_ok   = True
        self._internet_lock = threading.Lock()

        self._lock = threading.Lock()

        # Hardware init
        self.hardware = HardwareController()

        self._connect_firebase()

    # ─────────────────────────────────────────────────────
    # Firebase
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
            self.live_ref   = db.reference("/guardian_live")
            self.firebase_enabled = True
            logger.info(
                "Connected to Firebase Realtime Database at %s path=%s",
                DATABASE_URL,
                DRIVER_STATUS_PATH,
            )

        except ImportError:
            logger.error(
                "firebase_admin not installed.\n"
                "Run: pip install firebase-admin"
            )
        except Exception as exc:
            logger.error(f"Firebase connection failed: {exc}")

    # ─────────────────────────────────────────────────────
    # Internet check thread — non-blocking, every 5s
    # ─────────────────────────────────────────────────────

    def _internet_check_loop(self, interval: float = INTERNET_CHECK_INTERVAL) -> None:
        """
        Runs internet check in its own thread so it never blocks the
        FSR push loop or the poll loop. Hardware always responds.
        """
        while True:
            try:
                requests.get("https://google.com", timeout=3)
                ok = True
            except Exception:
                ok = False

            with self._internet_lock:
                if ok != self._internet_ok:
                    logger.info("Internet: %s", "ONLINE" if ok else "OFFLINE")
                self._internet_ok = ok

            time.sleep(interval)

    def _is_internet_ok(self) -> bool:
        with self._internet_lock:
            return self._internet_ok

    # ─────────────────────────────────────────────────────
    # FSR push thread — 200ms, hands_on_wheel
    # ─────────────────────────────────────────────────────

    def _fsr_push_loop(self, interval: float = FSR_PUSH_INTERVAL) -> None:
        """
        Reads the physical button every 200ms and pushes hands_on_wheel
        to Firebase so mobile sees near-instant on/off changes.
        Runs independently of the poll/stream loop.
        """
        logger.info("FSR push loop started (%.2fs interval)", interval)

        while True:
            try:
                hands = self.hardware.is_hands_on_wheel()

                # Share with main thread
                with self._fsr_lock:
                    self._latest_hands_on = hands

                # Write to same key the working version used
                if self.driver_ref and self._is_internet_ok():
                    self.driver_ref.update({"hands_on_wheel": hands})

            except Exception as exc:
                logger.error(f"FSR push error: {exc}")

            time.sleep(interval)

    # ─────────────────────────────────────────────────────
    # Live status thread — 1s, /guardian_live
    # ─────────────────────────────────────────────────────

    def _live_status_loop(self, interval: float = LIVE_STATUS_INTERVAL) -> None:
        """
        Writes the full current guardian state to /guardian_live every second.
        Mobile app listens to this node for a real-time dashboard.
        """
        logger.info("Live status loop started (%.1fs interval)", interval)

        while True:
            try:
                if self.live_ref and self._is_internet_ok():

                    with self._lock:
                        data = self._last_data.copy()

                    with self._fsr_lock:
                        hands = self._latest_hands_on

                    now = time.time()

                    danger_duration = None
                    if (
                        self._current_state in DANGER_STATES
                        and self._state_since is not None
                    ):
                        danger_duration = round(now - self._state_since, 1)

                    hands_off_duration = None
                    if self._hands_off_since is not None:
                        hands_off_duration = round(now - self._hands_off_since, 1)

                    live_payload = {
                        "driver_state":         self._current_state,
                        "hands_on_wheel":       hands,
                        "emotion":              data.get("emotion", "UNKNOWN"),
                        "avg_movement":         data.get("avg_movement"),
                        "eyes_closed_frames":   data.get("eyes_closed_frames"),
                        "danger_duration_s":    danger_duration,
                        "hands_off_duration_s": hands_off_duration,
                        "help_displayed":       self._help_displayed,
                        "escalated":            self._escalated,
                        "hands_off_threshold_s": HANDS_OFF_HELP_THRESHOLD_SECONDS,
                        "timestamp_iso":        datetime.now(timezone.utc).isoformat(),
                        "timestamp_epoch":      now,
                    }

                    self.live_ref.set(live_payload)

            except Exception as exc:
                logger.error(f"Live status write error: {exc}")

            time.sleep(interval)

    # ─────────────────────────────────────────────────────
    # Stream callback
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

            # Use latest FSR value already read by the push thread
            with self._fsr_lock:
                hands = self._latest_hands_on

            self._handle_state(state, emotion, hands, data)

        except Exception as exc:
            logger.error(f"Stream callback error: {exc}")

    # ─────────────────────────────────────────────────────
    # State handler
    # ─────────────────────────────────────────────────────

    def _handle_state(
        self,
        state: str,
        emotion: str,
        hands: bool,
        data: dict,
    ) -> None:

        now = time.time()

        # ── State transition ──────────────────────────────

        if state != self._current_state:

            logger.info(
                f"State change: {self._current_state} → {state} | "
                f"emotion={emotion} | "
                f"hands={'ON' if hands else 'OFF'}"
            )

            self._current_state = state
            self._escalated     = False

            # FIX: Do NOT reset _hands_off_since or _help_displayed here.
            # Rapid state flips (DIZZY→DISTRACTED→DIZZY every ~2s) were
            # resetting the hands-off timer on each transition, making it
            # impossible to ever reach the 30s threshold.
            # The timer now only resets when hands physically return to wheel.

            if state in DANGER_STATES:
                self._state_since = now
                logger.warning(f"⚠ DANGER state entered: {state}")
                self.hardware.buzz_alert(state)
                self.hardware.show_status_on_display(state)
            else:
                self._state_since = None
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
                self._write_alert_to_firebase(state, duration, data, hands)
                self._escalated = True

        # ── Hands-off wheel → HELP display ───────────────

        if not hands:

            # Start the timer only once — do not reset on state changes
            if self._hands_off_since is None:
                self._hands_off_since = now
                logger.warning(
                    f"🤚 Hands OFF wheel during {state} – "
                    f"HELP in {HANDS_OFF_HELP_THRESHOLD_SECONDS:.0f}s"
                )

            hands_off_duration = now - self._hands_off_since

            # Log progress every 5 seconds so it's easy to track in the log
            if int(hands_off_duration) % 5 == 0 and int(hands_off_duration) > 0:
                logger.info(
                    f"🤚 Hands still OFF wheel: {hands_off_duration:.1f}s / "
                    f"{HANDS_OFF_HELP_THRESHOLD_SECONDS:.0f}s"
                )

            if (
                hands_off_duration >= HANDS_OFF_HELP_THRESHOLD_SECONDS
                and not self._help_displayed
            ):
                logger.critical(
                    f"🆘 Hands off wheel for {hands_off_duration:.1f}s "
                    f"during {state} – HELP displayed"
                )

                print("\n" + "=" * 50)
                print("  🆘  HELP TRIGGERED  🆘")
                print(f"  STATE   : {state}")
                print(f"  HANDS   : OFF WHEEL for {hands_off_duration:.1f}s")
                print(f"  EMOTION : {data.get('emotion', 'UNKNOWN')}")
                print("  ACTION  : HELP displayed on matrix/LCD")
                print("  -> Firebase alert written")
                print("=" * 50 + "\n")

                self.hardware.buzz_alert("EMERGENCY")
                self.hardware.show_help_on_display()

                self._write_alert_to_firebase(
                    state="HANDS_OFF_EMERGENCY",
                    duration=hands_off_duration,
                    data=data,
                    hands=hands,
                )
                self._help_displayed = True

        else:
            # Hands are back on wheel — now it's safe to reset the timer
            if self._hands_off_since is not None or self._help_displayed:
                off_duration = (
                    round(now - self._hands_off_since, 1)
                    if self._hands_off_since is not None
                    else 0.0
                )
                logger.info(
                    f"✅ Hands returned to wheel after {off_duration}s – clearing HELP display"
                )
                self._hands_off_since = None
                self._help_displayed  = False
                if state in DANGER_STATES:
                    self.hardware.show_status_on_display(state)
                else:
                    self.hardware.clear_display()

    # ─────────────────────────────────────────────────────

    def _write_alert_to_firebase(
        self,
        state: str,
        duration: float,
        data: dict,
        hands: bool,
    ) -> None:

        if not self.firebase_enabled or self.alert_ref is None:
            return

        try:
            alert = {
                "state":              state,
                "duration_seconds":   round(duration, 1),
                "emotion":            data.get("emotion"),
                "hands_on_wheel":     hands,
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
    # Poll loop
    # ─────────────────────────────────────────────────────

    def _poll_loop(self, interval: float = POLL_INTERVAL) -> None:

        logger.info(f"Polling Firebase every {interval}s")

        while True:
            try:
                if not self._is_internet_ok():
                    logger.warning("No internet connection – skipping poll")
                    time.sleep(interval)
                    continue

                data = self.driver_ref.get()

                if isinstance(data, dict):
                    with self._lock:
                        self._last_data = data.copy()

                    state   = data.get("driver_state", "NORMAL")
                    emotion = data.get("emotion", "UNKNOWN")

                    # Use latest FSR value from push thread
                    with self._fsr_lock:
                        hands = self._latest_hands_on

                    self._handle_state(state, emotion, hands, data)

            except Exception as exc:
                logger.error(f"Polling error: {exc}")

            time.sleep(interval)

    # ─────────────────────────────────────────────────────
    # Run
    # ─────────────────────────────────────────────────────

    def run(self) -> None:

        if not self.firebase_enabled:
            logger.error("Firebase not connected.")
            return

        logger.info("GuardianDart starting all background threads...")
        logger.info(
            "Hands-off HELP threshold: %.0fs", HANDS_OFF_HELP_THRESHOLD_SECONDS
        )

        threads = [
            # Internet check — non-blocking, every 5s
            threading.Thread(
                target=self._internet_check_loop,
                args=(INTERNET_CHECK_INTERVAL,),
                daemon=True,
                name="internet-check",
            ),
            # FSR push — hands_on_wheel every 200ms
            threading.Thread(
                target=self._fsr_push_loop,
                args=(FSR_PUSH_INTERVAL,),
                daemon=True,
                name="fsr-push",
            ),
            # Live status — full guardian_live node every 1s
            threading.Thread(
                target=self._live_status_loop,
                args=(LIVE_STATUS_INTERVAL,),
                daemon=True,
                name="live-status",
            ),
        ]

        for t in threads:
            t.start()
            logger.info("Thread started: %s", t.name)

        try:
            if USE_FIREBASE_STREAM:
                self._listener = self.driver_ref.listen(self._on_data_change)
                while True:
                    time.sleep(1)
            else:
                logger.info(
                    "Firebase streaming disabled; using polling mode for Pi guardian alerts."
                )
                self._poll_loop()

        except KeyboardInterrupt:
            logger.info("GuardianDart stopped by user.")

        except Exception as exc:
            if USE_FIREBASE_STREAM:
                logger.error(f"Streaming failed: {exc}")
                logger.warning("Falling back to polling mode...")
                self._poll_loop()
            else:
                logger.error(f"Guardian polling failed: {exc}")

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