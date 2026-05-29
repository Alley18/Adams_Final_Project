"""Central configuration for the ADAMS improved backend.

The original backend used a hard-coded Windows CSV path. This module makes the
API portable across laptops, Raspberry Pi, cloud deployments, and mobile demos.
All values can be overridden with environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _split_csv(raw: str | None, default: Iterable[str]) -> list[str]:
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the API server."""

    app_name: str = "ADAMS Driver Assistant API"
    app_version: str = "4.0.0-major-upgrade"
    api_prefix: str = "/api/v1"
    project_root: Path = PROJECT_ROOT
    events_csv: Path = Path(os.getenv("ADAMS_EVENTS_CSV", PROJECT_ROOT / "logs" / "driving_history.csv"))
    conversation_csv: Path = Path(
        os.getenv("ADAMS_CONVERSATION_CSV", PROJECT_ROOT / "logs" / "conversation_history.csv")
    )
    websocket_interval_seconds: float = float(os.getenv("ADAMS_WS_INTERVAL_SECONDS", "1.0"))
    default_alert_limit: int = int(os.getenv("ADAMS_DEFAULT_ALERT_LIMIT", "25"))
    max_alert_limit: int = int(os.getenv("ADAMS_MAX_ALERT_LIMIT", "250"))
    cors_origins: tuple[str, ...] = tuple(_split_csv(os.getenv("ADAMS_CORS_ORIGINS"), ["*"]))

    def candidate_event_paths(self) -> list[Path]:
        """Return known event log paths in priority order."""
        return [
            self.events_csv,
            self.project_root / "logs" / "driving_history.csv",
            self.project_root / "ai_engine" / "logs" / "driving_history_old.csv",
        ]

    def active_events_path(self) -> Path:
        """Return the first available event CSV path, or the configured path."""
        for path in self.candidate_event_paths():
            if path.exists():
                return path
        return self.events_csv

    def active_conversation_path(self) -> Path:
        return self.conversation_csv


settings = Settings()
