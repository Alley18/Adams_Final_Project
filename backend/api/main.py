"""Compatibility entry point for ASGI deployments.

Run either of these commands:
    uvicorn backend.server:app --reload
    uvicorn backend.api.main:app --reload
"""

from backend.server import app

__all__ = ["app"]
