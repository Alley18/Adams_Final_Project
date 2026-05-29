# ADAMS Mobile App Major Upgrade Notes

This Flutter mobile client has been upgraded from a simple live-status viewer into a **driver safety command dashboard** that consumes the new backend analytics API.

## Major mobile improvements

| Area | Upgrade |
|---|---|
| Live command center | Added a redesigned home dashboard with current driver state, spoken AI output, risk score, buzzer state, session ID, and core safety metrics. |
| Adaptive layout | Added responsive navigation: bottom navigation for phones and navigation rail for tablets/desktops. |
| Monitoring screen | Added a focused high-risk monitoring page with risk bar, trigger, buzzer, AI speech, recommended action, and suggested route. |
| Analytics screen | Added backend-driven totals, danger/warning counts, distracted/drowsy counts, level breakdowns, driver-state breakdowns, and safety recommendations. |
| Alert feed | Expanded alert cards with risk score, severity, trigger, suggested route, driver state, session ID, buzzer status, and high-risk visual highlighting. |
| Trip sessions | Added session summary screen using `/api/v1/sessions` to show event totals, warnings, danger events, and highest risk by trip/session. |
| Conversation history | Added conversation timeline integration using `/api/v1/conversation`. |
| System tools | Added backend URL configuration, refresh controls, schema viewer, backend config viewer, latency display, and manual test-warning creation. |
| Networking | Rebuilt the mobile API service to poll the upgraded backend endpoints, merge real-time alerts, track health, expose analytics, and handle degraded backend states gracefully. |

## Backend endpoints used by the mobile app

| Endpoint | Purpose |
|---|---|
| `/health` | Backend health, row count, and log-path status. |
| `/state` | Latest normalized driver event for legacy compatibility. |
| `/api/v1/alerts?limit=100` | Recent safety events for the alert feed. |
| `/api/v1/analytics?limit=100` | Aggregate safety metrics and recommendations. |
| `/api/v1/sessions` | Trip/session safety summaries. |
| `/api/v1/conversation?limit=30` | Driver/assistant conversation history. |
| `/api/v1/config` | Backend metadata and active paths. |
| `/schema` | Legacy and normalized schema information. |
| `/api/v1/events` | Manual test event creation from the System screen. |

## Running the upgraded mobile app

Run the backend first:

```bash
cd backend
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Then run the Flutter app:

```bash
cd frontend/dashboard/mobile_live_client_only
flutter pub get
flutter run
```

On a real phone, open the backend URL dialog in the app and replace `127.0.0.1` with the computer or Raspberry Pi IP address that is running the backend, for example `http://192.168.1.20:8000`.
