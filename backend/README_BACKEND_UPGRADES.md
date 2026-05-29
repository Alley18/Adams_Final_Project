# ADAMS Backend Major Upgrade

This backend has been upgraded from a small CSV reader into a stronger mobile-ready API layer for the AI driver assistant project.

## What changed

The previous server depended on a hard-coded Windows file path and exposed only four simple endpoints. The upgraded backend now uses a cross-platform configuration layer, versioned endpoints, analytics, sessions, conversation history, manual event logging, export support, and WebSocket live updates while preserving the original mobile endpoints.

| Area | Upgrade |
| --- | --- |
| Portability | Uses `ADAMS_EVENTS_CSV` and `ADAMS_CONVERSATION_CSV` environment variables, with project-local fallbacks. |
| API structure | Adds `/api/v1/*` endpoints while keeping `/health`, `/state`, `/alerts`, and `/schema`. |
| Safety analytics | Adds counts, risk scores, state breakdowns, recent timeline, and safety recommendations. |
| Mobile readiness | Stable normalized JSON contract for current state, alerts, analytics, and live WebSocket streaming. |
| Operations | Adds `/api/v1/config`, CSV export, and a compatibility import path at `backend/api/main.py`. |
| Testing/demo | Adds `POST /api/v1/events` so developers can create manual events without running the camera pipeline. |

## Run locally

```bash
pip install -r requirements.txt
uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

Open the API documentation at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Important endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Legacy health endpoint used by the original mobile app. |
| `GET /state` | Latest normalized driver state. |
| `GET /alerts?limit=25` | Latest alerts, newest first. |
| `GET /api/v1/analytics` | Driver-safety statistics and recommendations. |
| `GET /api/v1/sessions` | Trip/session summaries from the event log. |
| `GET /api/v1/conversation` | Recent driver/ADAMS conversation turns. |
| `POST /api/v1/events` | Add a manual or test safety event. |
| `GET /api/v1/export/events.csv` | Download normalized events as CSV. |
| `WS /ws/state` | Live state and analytics stream for future real-time clients. |

## Configure log paths

```bash
export ADAMS_EVENTS_CSV=/absolute/path/to/logs/driving_history.csv
export ADAMS_CONVERSATION_CSV=/absolute/path/to/logs/conversation_history.csv
export ADAMS_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:8000
```

If no environment variables are set, the API looks for `logs/driving_history.csv` inside the project first.
