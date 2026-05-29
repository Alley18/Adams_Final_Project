"""ADAMS Driver Assistant upgraded backend.

Major improvements included in this version:
- Cross-platform log path handling instead of a hard-coded Windows CSV path.
- Versioned REST API under /api/v1 while keeping legacy /health, /state,
  /alerts, and /schema endpoints for the existing mobile app.
- Rich safety analytics, sessions, conversation history, manual event logging,
  CSV export, and WebSocket live-state streaming.
- Strong Pydantic response models and a service layer that normalizes legacy CSV
  rows into one stable mobile contract.
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Annotated

from fastapi import APIRouter, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.core.config import settings
from backend.models.schemas import (
    AnalyticsSummary,
    BackendConfigResponse,
    EventCreate,
    EventCreateResponse,
    HealthResponse,
    SchemaResponse,
)
from backend.services import log_reader


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Improved ADAMS backend for live AI driver monitoring, analytics, and mobile dashboards.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix=settings.api_prefix, tags=["ADAMS v1"])

LimitQuery = Annotated[int, Query(ge=1, le=settings.max_alert_limit)]


@app.get("/", tags=["Legacy"])
def root() -> dict[str, str]:
    return {
        "message": "ADAMS Live Backend Running",
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_prefix,
    }


@router.get("/config", response_model=BackendConfigResponse)
def backend_config() -> BackendConfigResponse:
    return BackendConfigResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        api_prefix=settings.api_prefix,
        events_csv=str(settings.active_events_path()),
        conversation_csv=str(settings.active_conversation_path()),
        cors_origins=list(settings.cors_origins),
        websocket_endpoint="/ws/state",
    )


@router.get("/health", response_model=HealthResponse)
def health() -> dict:
    return log_reader.health_payload()


@router.get("/state")
def state() -> dict:
    return log_reader.latest_state().model_dump()


@router.get("/alerts")
def alerts(
    limit: LimitQuery = settings.default_alert_limit,
    level: str | None = Query(default=None, description="Optional level filter such as WARNING or DANGER."),
    session_id: str | None = Query(default=None, description="Optional session filter."),
) -> list[dict]:
    return [item.model_dump() for item in log_reader.filtered_events(limit=limit, level=level, session_id=session_id)]


@router.get("/events")
def events(
    limit: LimitQuery = 100,
    level: str | None = None,
    session_id: str | None = None,
) -> list[dict]:
    return [item.model_dump() for item in log_reader.filtered_events(limit=limit, level=level, session_id=session_id)]


@router.post("/events", response_model=EventCreateResponse, status_code=201)
def create_event(payload: EventCreate) -> EventCreateResponse:
    event = log_reader.append_event(payload.to_row())
    return EventCreateResponse(status="created", event=event)


@router.get("/analytics", response_model=AnalyticsSummary)
def analytics(limit: LimitQuery = 100) -> AnalyticsSummary:
    return log_reader.analytics(limit=limit)


@router.get("/sessions")
def sessions() -> list[dict]:
    return log_reader.sessions()


@router.get("/conversation")
def conversation(
    limit: LimitQuery = 50,
    session_id: str | None = Query(default=None, description="Optional session filter."),
) -> list[dict]:
    return [turn.model_dump() for turn in log_reader.conversation(limit=limit, session_id=session_id)]


@router.get("/schema", response_model=SchemaResponse)
def schema() -> dict:
    return log_reader.schema_info()


@router.get("/export/events.csv")
def export_events_csv(limit: LimitQuery = settings.max_alert_limit) -> StreamingResponse:
    rows = [item.model_dump() for item in log_reader.filtered_events(limit=limit)]
    buffer = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else list(log_reader.EVENT_FIELDS)
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=adams_events_export.csv"},
    )


@app.websocket("/ws/state")
async def websocket_state(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(
                {
                    "state": log_reader.latest_state().model_dump(),
                    "analytics": log_reader.analytics(limit=50).model_dump(),
                }
            )
            await asyncio.sleep(settings.websocket_interval_seconds)
    except WebSocketDisconnect:
        return


# Versioned routes.
app.include_router(router)


# Legacy compatibility routes used by the original mobile app.
@app.get("/health", tags=["Legacy"])
def legacy_health() -> dict:
    return health()


@app.get("/state", tags=["Legacy"])
def legacy_state() -> dict:
    return state()


@app.get("/alerts", tags=["Legacy"])
def legacy_alerts(limit: int = settings.default_alert_limit) -> list[dict]:
    safe_limit = max(1, min(limit, settings.max_alert_limit))
    return [item.model_dump() for item in log_reader.filtered_events(limit=safe_limit)]


@app.get("/schema", tags=["Legacy"])
def legacy_schema() -> dict:
    return schema()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000, reload=True)
