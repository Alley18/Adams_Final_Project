"""Pydantic schemas for the ADAMS improved backend API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DriverState(BaseModel):
    timestamp: str = ""
    input: str = ""
    level: str = "INFO"
    message: str = "Monitoring"
    spoken_text: str = "Monitoring"
    buzzer: bool = False
    driver_state: str = "Monitoring"
    trigger: str = ""
    suggested_route: str = "N/A"
    recommended_action: str = "Keep monitoring the driver."
    session_id: str = "unknown"
    source_path: str = ""
    risk_score: int = Field(default=0, ge=0, le=100)
    event_id: str = ""


class AlertItem(DriverState):
    severity_rank: int = Field(default=0, ge=0, le=4)


class HealthResponse(BaseModel):
    status: str
    version: str
    rows_loaded: int
    events_csv: str
    conversation_csv: str
    current_session_id: str = "unknown"
    latest_timestamp: str = ""
    warnings: list[str] = Field(default_factory=list)
    uptime_hint: str = "API is ready. Connect the mobile app to this base URL."


class SchemaResponse(BaseModel):
    columns: list[str]
    normalized_fields: list[str]
    endpoints: dict[str, str]


class AnalyticsSummary(BaseModel):
    total_events: int = 0
    danger_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    buzzer_activations: int = 0
    distracted_count: int = 0
    drowsy_count: int = 0
    latest_risk_score: int = 0
    highest_risk_score: int = 0
    current_session_id: str = "unknown"
    first_event: str = "N/A"
    last_event: str = "N/A"
    level_breakdown: dict[str, int] = Field(default_factory=dict)
    driver_state_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_timeline: list[dict[str, Any]] = Field(default_factory=list)
    safety_recommendations: list[str] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    session_id: str = "unknown"
    timestamp: str = ""
    role: str = "driver"
    text: str = ""
    driver_state: str = ""


class EventCreate(BaseModel):
    input: str = ""
    level: str = "INFO"
    message: str = "Manual event"
    spoken_text: str | None = None
    buzzer: bool = False
    driver_state: str = "Monitoring"
    trigger: str = "manual"
    suggested_route: str = "N/A"
    session_id: str | None = None
    timestamp: str | None = None

    def to_row(self) -> dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "session_id": self.session_id or "manual",
            "timestamp": self.timestamp or now,
            "input": self.input,
            "level": self.level.upper(),
            "message": self.message,
            "spoken_text": self.spoken_text or self.message,
            "buzzer": self.buzzer,
            "driver_state": self.driver_state,
            "trigger": self.trigger,
            "suggested_route": self.suggested_route,
        }


class EventCreateResponse(BaseModel):
    status: str
    event: DriverState


class BackendConfigResponse(BaseModel):
    app_name: str
    app_version: str
    api_prefix: str
    events_csv: str
    conversation_csv: str
    cors_origins: list[str]
    websocket_endpoint: str
