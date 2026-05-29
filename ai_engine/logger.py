"""
ADAMS Event Logger
==================
Persists driver-state events, AI safety responses, and conversational
assistant turns to rolling CSV log files.

Upgrades over v2.1:
  - Session IDs: every power-on gets a UUID so you can replay a full trip.
  - log_conversation(): captures chat() turns from AdamsBrain v3.
  - get_trip_summary(): returns stats for the current (or any past) session.
  - Separate CSV for conversation history to keep the safety log clean.
  - Thread-safe: a module-level lock protects all file writes.

Authors : ADAMS Team
Version : 3.0.0
"""

import csv
import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("adams.logger")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LOG_DIR:           Path = Path("logs")
EVENTS_LOG:        Path = LOG_DIR / "driving_history.csv"
CONVERSATION_LOG:  Path = LOG_DIR / "conversation_history.csv"

# ---------------------------------------------------------------------------
# CSV schemas
# ---------------------------------------------------------------------------
_EVENT_FIELDS: tuple[str, ...] = (
    "session_id",
    "timestamp",
    "input",
    "level",
    "message",
    "spoken_text",
    "buzzer",
    "driver_state",
    "trigger",
    "suggested_route",
)

_CONVERSATION_FIELDS: tuple[str, ...] = (
    "session_id",
    "timestamp",
    "role",          # "driver" | "adams"
    "text",
    "driver_state",  # telemetry snapshot at time of utterance
)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_write_lock   = threading.Lock()
_session_id   = str(uuid.uuid4())[:8]   # short 8-char ID, e.g. "a3f9c21b"

logger.info("ADAMS Logger session: %s", _session_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def new_session() -> str:
    """
    Start a fresh session (call at the beginning of each new trip).
    Returns the new session ID.
    """
    global _session_id
    _session_id = str(uuid.uuid4())[:8]
    logger.info("New ADAMS session started: %s", _session_id)
    return _session_id


def current_session() -> str:
    """Return the current session ID."""
    return _session_id


def log_event(detection: str, ai_response_json: str) -> bool:
    """
    Append a single safety event row to driving_history.csv.

    Parameters
    ----------
    detection : str
        Either plain telemetry text or a JSON string with structured alert data.
    ai_response_json : str
        JSON string from AdamsBrain.generate_advice().

    Returns
    -------
    bool
        True on success, False if the write failed.
    """
    try:
        detection_data = _parse_json(detection)
        ai_data        = _parse_json(ai_response_json)

        row = {
            "session_id":     _session_id,
            "timestamp":      _now(),
            "input":          "",
            "level":          "INFO",
            "message":        "",
            "spoken_text":    "",
            "buzzer":         False,
            "driver_state":   "Monitoring",
            "trigger":        "",
            "suggested_route":"N/A",
        }

        # Detection side
        if isinstance(detection_data, dict):
            row["timestamp"]    = str(detection_data.get("timestamp",    row["timestamp"]))
            row["input"]        = str(detection_data.get("input",        ""))
            row["level"]        = str(detection_data.get("level",        row["level"]))
            row["message"]      = str(detection_data.get("message",      ""))
            row["spoken_text"]  = str(
                detection_data.get("spoken_text")
                or detection_data.get("message") or ""
            )
            row["buzzer"]       = _to_bool(detection_data.get("buzzer", False))
            row["driver_state"] = str(
                detection_data.get("driver_state")
                or detection_data.get("trigger")
                or row["driver_state"]
            )
            row["trigger"]      = str(detection_data.get("trigger", ""))
        else:
            row["input"] = str(detection).strip()

        # AI response side
        if isinstance(ai_data, dict):
            row["level"]          = str(ai_data.get("level",          row["level"]))
            row["message"]        = str(ai_data.get("message",        row["message"]))
            row["spoken_text"]    = str(
                ai_data.get("spoken_text")
                or ai_data.get("message")
                or row["spoken_text"]
            )
            row["buzzer"]         = _to_bool(
                ai_data.get("buzzer", ai_data.get("buzzer_active", row["buzzer"]))
            )
            row["suggested_route"]= str(ai_data.get("suggested_route", row["suggested_route"]))
            row["driver_state"]   = str(ai_data.get("driver_state",    row["driver_state"]))

        # Cross-fill message ↔ spoken_text
        if not row["message"]     and row["spoken_text"]: row["message"]     = row["spoken_text"]
        if not row["spoken_text"] and row["message"]:     row["spoken_text"] = row["message"]

        _write_row(EVENTS_LOG, _EVENT_FIELDS, row)
        logger.debug("Event logged [%s]: %s", row["level"], row["message"])
        return True

    except Exception:
        logger.exception("log_event failed — event NOT saved")
        return False


def log_conversation(role: str, text: str, driver_state: str = "") -> bool:
    """
    Append a single conversation turn to conversation_history.csv.

    Call this after every AdamsBrain.chat() exchange so you have a full
    transcript of the driver ↔ ADAMS dialogue per trip.

    Parameters
    ----------
    role : str
        "driver" for what the driver said, "adams" for ADAMS's reply.
    text : str
        The spoken text.
    driver_state : str, optional
        Telemetry snapshot at the time of this utterance (for context).

    Returns
    -------
    bool
        True on success.
    """
    try:
        row = {
            "session_id":   _session_id,
            "timestamp":    _now(),
            "role":         role.lower().strip(),
            "text":         text.strip(),
            "driver_state": driver_state.strip(),
        }
        _write_row(CONVERSATION_LOG, _CONVERSATION_FIELDS, row)
        logger.debug("Conversation logged [%s]: %r", role, text[:60])
        return True
    except Exception:
        logger.exception("log_conversation failed — turn NOT saved")
        return False


def read_recent_events(n: int = 50, session_id: Optional[str] = None) -> list[dict]:
    """
    Return the most recent N safety events, newest first.

    Parameters
    ----------
    n : int
        Maximum number of rows to return.
    session_id : str, optional
        Filter to a specific session. Defaults to all sessions.
    """
    return _read_recent(EVENTS_LOG, n, session_id)


def read_recent_conversation(n: int = 50, session_id: Optional[str] = None) -> list[dict]:
    """
    Return the most recent N conversation turns, newest first.
    """
    return _read_recent(CONVERSATION_LOG, n, session_id)


def get_trip_summary(session_id: Optional[str] = None) -> dict:
    """
    Return a stats summary for a session (defaults to the current one).

    Returns a dict with:
      session_id        – which session
      total_events      – total safety events logged
      danger_count      – number of DANGER-level events
      warning_count     – number of WARNING-level events
      buzzer_activations– how many times the buzzer fired
      chat_turns        – total conversation turns (driver + adams combined)
      driver_turns      – how many times the driver spoke
      first_event       – timestamp of first event
      last_event        – timestamp of last event
    """
    sid = session_id or _session_id
    events       = _read_all(EVENTS_LOG,       sid)
    convo_rows   = _read_all(CONVERSATION_LOG, sid)

    danger_count  = sum(1 for r in events if r.get("level") == "DANGER")
    warning_count = sum(1 for r in events if r.get("level") == "WARNING")
    buzzer_count  = sum(1 for r in events if _to_bool(r.get("buzzer", False)))
    driver_turns  = sum(1 for r in convo_rows if r.get("role") == "driver")

    timestamps = [r["timestamp"] for r in events if r.get("timestamp")]

    return {
        "session_id":         sid,
        "total_events":       len(events),
        "danger_count":       danger_count,
        "warning_count":      warning_count,
        "buzzer_activations": buzzer_count,
        "chat_turns":         len(convo_rows),
        "driver_turns":       driver_turns,
        "first_event":        min(timestamps) if timestamps else "N/A",
        "last_event":         max(timestamps) if timestamps else "N/A",
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_json(raw: str) -> Optional[dict]:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _to_bool(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _write_row(path: Path, fieldnames: tuple, row: dict) -> None:
    """Thread-safe append of a single row to a CSV file."""
    _ensure_log_dir()
    with _write_lock:
        is_new = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if is_new:
                writer.writeheader()
            writer.writerow(row)


def _read_recent(path: Path, n: int, session_id: Optional[str]) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if session_id:
            rows = [r for r in rows if r.get("session_id") == session_id]
        return rows[-n:][::-1]
    except Exception:
        logger.exception("Failed to read %s", path)
        return []


def _read_all(path: Path, session_id: Optional[str]) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if session_id:
            rows = [r for r in rows if r.get("session_id") == session_id]
        return rows
    except Exception:
        logger.exception("Failed to read %s", path)
        return []


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.DEBUG)

    print(f"Session: {current_session()}")

    # Safety event
    detection = json.dumps({
        "timestamp":    "2026-05-07 09:10:00",
        "trigger":      "CAMERA_DROWSY",
        "input":        "Eyes closed 2.1s",
        "level":        "DANGER",
        "message":      "Pull over now.",
        "spoken_text":  "Pull over now.",
        "buzzer":       True,
        "driver_state": "Drowsy",
    })
    response = json.dumps({
        "level":          "DANGER",
        "message":        "Please pull over safely and rest.",
        "buzzer_active":  True,
        "suggested_route":"REST_STOP",
    })
    print("Safety event logged:", log_event(detection, response))

    # Conversation turns
    telemetry = "Eye openness: 10%, Drowsy: True"
    print("Driver turn logged:", log_conversation("driver", "How far is the next rest stop?", telemetry))
    print("ADAMS turn logged: ", log_conversation("adams",  "About 12 km ahead — I'd strongly recommend we pull in.", telemetry))

    time.sleep(0.1)

    # Trip summary
    summary = get_trip_summary()
    print("\nTrip Summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")