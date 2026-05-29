"""Log access, normalization, and analytics utilities for the ADAMS API."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from backend.core.config import settings
from backend.models.schemas import AnalyticsSummary, AlertItem, ConversationTurn, DriverState


EVENT_FIELDS = [
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
]


def to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on", "active"}


def severity_rank(level: str) -> int:
    normalized = (level or "INFO").upper()
    return {"CRITICAL": 4, "DANGER": 3, "WARNING": 2, "INFO": 1}.get(normalized, 0)


def risk_score(level: str, buzzer: bool, driver_state: str, trigger: str) -> int:
    base = {"CRITICAL": 100, "DANGER": 85, "WARNING": 55, "INFO": 15}.get((level or "INFO").upper(), 20)
    text = f"{driver_state} {trigger}".lower()
    if "drows" in text or "sleep" in text:
        base += 10
    if "distract" in text or "phone" in text:
        base += 8
    if buzzer:
        base += 7
    return max(0, min(base, 100))


def recommended_action(level: str, buzzer: bool, driver_state: str) -> str:
    text = driver_state.lower()
    normalized = (level or "INFO").upper()
    if normalized in {"CRITICAL", "DANGER"} or buzzer:
        if "drows" in text or "sleep" in text:
            return "Ask the driver to pull over safely, rest, and keep the alarm active until attention recovers."
        if "distract" in text or "phone" in text:
            return "Tell the driver to return eyes to the road and stop non-driving activity immediately."
        return "Escalate the alert, reduce speed if safe, and prepare to stop in a safe location."
    if normalized == "WARNING":
        return "Warn the driver early, increase monitoring sensitivity, and keep both hands and eyes focused."
    return "Continue passive monitoring and keep the dashboard connected."


def event_id(row: dict[str, Any]) -> str:
    raw = "|".join(str(row.get(key, "")) for key in ["session_id", "timestamp", "input", "level", "message"])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_event(raw: dict[str, Any] | None, source_path: str = "") -> DriverState:
    row = raw or {}
    message = str(
        row.get("spoken_text")
        or row.get("speech")
        or row.get("ai_text")
        or row.get("message")
        or "Monitoring"
    ).strip()
    backend_message = str(row.get("message") or message or "Monitoring").strip()
    trigger = str(row.get("trigger", "")).strip()
    driver_state = str(
        row.get("driver_state")
        or row.get("driverState")
        or trigger
        or backend_message
        or "Monitoring"
    ).strip()
    level = str(row.get("level") or "INFO").strip().upper()
    buzzer = to_bool(row.get("buzzer", row.get("buzzer_active", False)))
    normalized = {
        "timestamp": str(row.get("timestamp", "")),
        "input": str(row.get("input", "")),
        "level": level,
        "message": backend_message,
        "spoken_text": message,
        "buzzer": buzzer,
        "driver_state": driver_state,
        "trigger": trigger,
        "suggested_route": str(row.get("suggested_route", "N/A") or "N/A"),
        "recommended_action": recommended_action(level, buzzer, driver_state),
        "session_id": str(row.get("session_id", "unknown") or "unknown"),
        "source_path": source_path,
        "risk_score": risk_score(level, buzzer, driver_state, trigger),
    }
    normalized["event_id"] = event_id(normalized)
    return DriverState(**normalized)


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for raw in reader:
            row = dict(raw)
            row.pop(None, None)  # discard overflow cells from legacy malformed rows
            rows.append(row)
        return rows


def _header(path: Path) -> list[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _ensure_event_schema(path: Path) -> None:
    """Upgrade old CSV headers to the richer backend schema before append."""
    current_header = _header(path)
    if not current_header or current_header == EVENT_FIELDS:
        return
    migrated = [normalize_event(row, str(path)).model_dump() for row in read_csv_rows(path)]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for item in migrated:
            writer.writerow({field: item.get(field, "") for field in EVENT_FIELDS})


def append_event(row: dict[str, Any]) -> DriverState:
    path = settings.active_events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_event_schema(path)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in EVENT_FIELDS})
    return normalize_event(row, str(path))


def all_events() -> list[DriverState]:
    path = settings.active_events_path()
    rows = read_csv_rows(path)
    return [normalize_event(row, str(path)) for row in rows]


def latest_state() -> DriverState:
    events = all_events()
    if not events:
        return normalize_event({"message": "No data yet", "spoken_text": "No data yet"}, str(settings.active_events_path()))
    return events[-1]


def filtered_events(limit: int = 50, level: str | None = None, session_id: str | None = None) -> list[AlertItem]:
    limit = max(1, min(limit, settings.max_alert_limit))
    events = all_events()
    if level:
        events = [event for event in events if event.level.upper() == level.upper()]
    if session_id:
        events = [event for event in events if event.session_id == session_id]
    newest = list(reversed(events))[:limit]
    return [AlertItem(**event.model_dump(), severity_rank=severity_rank(event.level)) for event in newest]


def schema_info() -> dict[str, Any]:
    path = settings.active_events_path()
    rows = read_csv_rows(path)
    columns = list(rows[0].keys()) if rows else EVENT_FIELDS
    return {
        "columns": columns,
        "normalized_fields": list(DriverState.model_fields.keys()),
        "endpoints": {
            "health": "/health and /api/v1/health",
            "state": "/state and /api/v1/state",
            "alerts": "/alerts and /api/v1/alerts?limit=25",
            "analytics": "/api/v1/analytics",
            "sessions": "/api/v1/sessions",
            "conversation": "/api/v1/conversation",
            "websocket": "/ws/state",
        },
    }


def health_payload() -> dict[str, Any]:
    events = all_events()
    path = settings.active_events_path()
    warnings: list[str] = []
    if not path.exists():
        warnings.append("Event CSV does not exist yet; start the vision pipeline or post a manual event.")
    if str(path).startswith("C:\\"):
        warnings.append("The event CSV still points to a Windows-only path; set ADAMS_EVENTS_CSV for deployment.")
    current_session = events[-1].session_id if events else "unknown"
    latest_timestamp = events[-1].timestamp if events else ""
    return {
        "status": "ok" if path.exists() else "degraded",
        "version": settings.app_version,
        "rows_loaded": len(events),
        "events_csv": str(path),
        "conversation_csv": str(settings.active_conversation_path()),
        "current_session_id": current_session,
        "latest_timestamp": latest_timestamp,
        "warnings": warnings,
    }


def sessions() -> list[dict[str, Any]]:
    grouped: dict[str, list[DriverState]] = {}
    for event in all_events():
        grouped.setdefault(event.session_id, []).append(event)
    output: list[dict[str, Any]] = []
    for session_id, events in grouped.items():
        output.append(
            {
                "session_id": session_id,
                "events": len(events),
                "danger_count": sum(1 for event in events if event.level == "DANGER"),
                "warning_count": sum(1 for event in events if event.level == "WARNING"),
                "buzzer_activations": sum(1 for event in events if event.buzzer),
                "highest_risk_score": max((event.risk_score for event in events), default=0),
                "first_event": events[0].timestamp if events else "N/A",
                "last_event": events[-1].timestamp if events else "N/A",
            }
        )
    return sorted(output, key=lambda row: row.get("last_event", ""), reverse=True)


def conversation(limit: int = 50, session_id: str | None = None) -> list[ConversationTurn]:
    path = settings.active_conversation_path()
    rows = read_csv_rows(path)
    if session_id:
        rows = [row for row in rows if row.get("session_id") == session_id]
    newest = list(reversed(rows))[: max(1, min(limit, settings.max_alert_limit))]
    return [ConversationTurn(**row) for row in newest]


def analytics(limit: int = 100) -> AnalyticsSummary:
    events = all_events()
    recent = events[-max(1, min(limit, settings.max_alert_limit)) :]
    levels = Counter(event.level for event in events)
    states = Counter(event.driver_state for event in events)
    danger = levels.get("DANGER", 0) + levels.get("CRITICAL", 0)
    warning = levels.get("WARNING", 0)
    buzzer_count = sum(1 for event in events if event.buzzer)
    latest = events[-1] if events else normalize_event({})
    timeline = [
        {
            "timestamp": event.timestamp,
            "level": event.level,
            "driver_state": event.driver_state,
            "risk_score": event.risk_score,
            "buzzer": event.buzzer,
        }
        for event in recent[-20:]
    ]
    recommendations: list[str] = []
    if danger:
        recommendations.append("Review DANGER events first and tune drowsiness/distraction thresholds if false positives occur.")
    if buzzer_count:
        recommendations.append("Verify the physical buzzer relay and mobile warning flow because buzzer events were recorded.")
    if warning and not danger:
        recommendations.append("Warnings are present without danger escalation; continue collecting data for threshold calibration.")
    if not events:
        recommendations.append("No live events were found. Start backend/detection/vision_node.py to feed the dashboard.")
    return AnalyticsSummary(
        total_events=len(events),
        danger_count=danger,
        warning_count=warning,
        info_count=levels.get("INFO", 0),
        buzzer_activations=buzzer_count,
        distracted_count=sum(1 for event in events if "distract" in f"{event.driver_state} {event.trigger}".lower()),
        drowsy_count=sum(1 for event in events if "drows" in f"{event.driver_state} {event.trigger}".lower()),
        latest_risk_score=latest.risk_score,
        highest_risk_score=max((event.risk_score for event in events), default=0),
        current_session_id=latest.session_id,
        first_event=events[0].timestamp if events else "N/A",
        last_event=events[-1].timestamp if events else "N/A",
        level_breakdown=dict(levels),
        driver_state_breakdown=dict(states),
        recent_timeline=timeline,
        safety_recommendations=recommendations,
    )


def rows_as_dicts(items: Iterable[DriverState]) -> list[dict[str, Any]]:
    return [item.model_dump() for item in items]
