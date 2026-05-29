# AI Driver Assistant — Major Improved Build

This version adds major backend and mobile upgrades while preserving the original project structure.

## Backend improvements

| Area | Improvement |
|---|---|
| Architecture | Added `backend/core`, `backend/models`, and `backend/services` modules so the backend is no longer a single thin server file. |
| API design | Added versioned `/api/v1` endpoints while keeping legacy `/state`, `/alerts`, and `/schema` endpoints compatible. |
| Data normalization | Added robust CSV log reading, event normalization, deterministic event IDs, severity ranks, risk scores, session fields, and safe handling of old log formats. |
| Analytics | Added `/api/v1/analytics` with total events, danger/warning/info counts, buzzer activations, drowsy/distracted counts, risk scores, breakdowns, timeline, and recommendations. |
| Sessions | Added `/api/v1/sessions` to summarize driving sessions/trips. |
| Conversation | Added `/api/v1/conversation` to expose assistant/driver conversation logs when present. |
| Manual events | Added `POST /api/v1/events` so the app or developers can create test/manual safety events. |
| Export | Added `/api/v1/export/events.csv` for normalized CSV export. |
| Real-time | Added `/ws/state` WebSocket endpoint for future live clients. |
| Reliability | Added health/config endpoints, configurable paths, CORS settings, validation script, and backend upgrade documentation. |

## Mobile app improvements

| Area | Improvement |
|---|---|
| UI/UX | Rebuilt the Flutter app as a command dashboard with a modern dark safety interface. |
| Navigation | Added adaptive navigation with bottom tabs on phones and a navigation rail on large screens. |
| Live monitoring | Added risk score, driver state, buzzer state, spoken output, trigger, route, and recommended action displays. |
| Analytics | Added live analytics, breakdown cards, safety recommendations, and risk metrics from the upgraded backend. |
| Alerts | Expanded alert cards with risk scores, severity, session, driver state, trigger, route, and high-risk highlighting. |
| Trips | Added trip/session summaries. |
| System tools | Added backend URL editing, health/latency display, schema/config viewers, refresh controls, and manual test-warning creation. |
| Models/services | Added richer Dart models and upgraded the API service to consume all major new backend endpoints. |

## Key documentation files

| File | Purpose |
|---|---|
| `backend/README_BACKEND_UPGRADES.md` | Explains backend architecture, endpoints, and run commands. |
| `frontend/dashboard/mobile_live_client_only/README_MOBILE_UPGRADES.md` | Explains mobile screens, endpoint usage, and run commands. |
| `backend/validate_backend.py` | Quick backend validation script. |
| `tools_validate_mobile.py` | Lightweight source validator used because Flutter/Dart tooling was not installed in the sandbox. |

## Suggested run order

```bash
cd backend
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Then open the mobile project:

```bash
cd frontend/dashboard/mobile_live_client_only
flutter pub get
flutter run
```

On a physical phone, set the app backend URL to the computer/Raspberry Pi IP address instead of `127.0.0.1`.
