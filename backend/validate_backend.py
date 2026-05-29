"""Quick validation script for the upgraded ADAMS backend."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.server import app


def main() -> None:
    client = TestClient(app)
    for path in [
        "/",
        "/health",
        "/state",
        "/alerts",
        "/schema",
        "/api/v1/config",
        "/api/v1/analytics",
        "/api/v1/sessions",
        "/api/v1/conversation",
        "/api/v1/export/events.csv",
    ]:
        response = client.get(path)
        print(path, response.status_code, response.text[:180].replace("\n", " "))
        assert response.status_code == 200, path

    response = client.post(
        "/api/v1/events",
        json={
            "level": "WARNING",
            "message": "Manual backend upgrade validation event",
            "driver_state": "Distracted",
            "buzzer": False,
        },
    )
    print("/api/v1/events POST", response.status_code, response.text[:180].replace("\n", " "))
    assert response.status_code == 201


if __name__ == "__main__":
    main()
