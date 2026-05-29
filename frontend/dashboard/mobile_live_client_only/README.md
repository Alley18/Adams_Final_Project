# ADAMS Mobile Live Client (Flutter)

This ZIP contains **only the mobile app**.

It does **not** recreate or copy `Project01`.
It does **not** include backend code.
It does **not** modify the logs.

## What this app does
- Pulls live data from your server every 1 second.
- Displays the newest driver state, alerts, and schema.
- Lets you change the backend URL from inside the app.

## Expected backend endpoints
Your separate server should expose:
- `GET /health`
- `GET /state`
- `GET /alerts`
- `GET /schema`

Example base URL:
- `http://192.168.0.10:8000`

## Run
```bash
flutter pub get
flutter run -d chrome
```

For phone browser testing:
```bash
flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8080
```

Then open the app in the phone browser and set the backend URL to your server IP.
