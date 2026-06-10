"""
ADAMS route server.

Small HTTP server used by the Flutter Mood Route screen.

Endpoint:
    POST /route

Body:
    {
        "origin": "longitude,latitude",
        "destination": "longitude,latitude",
        "emotion": "relaxed|happy|stressed|tired|focused|neutral"
    }

Response includes OSRM route geometry + POI score from Overpass API.
POI score = how many emotion-matched places exist near the route.
This is the layer system that connects emotion to real map data.
"""

from __future__ import annotations

import json
import logging
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


HOST = os.getenv("ADAMS_ROUTE_HOST", "0.0.0.0")
PORT = int(os.getenv("ADAMS_ROUTE_PORT", "5000"))
OSRM_BASE_URL = os.getenv(
    "ADAMS_OSRM_BASE_URL",
    "https://router.project-osrm.org/route/v1/driving",
)
REQUEST_TIMEOUT_SECONDS = float(os.getenv("ADAMS_ROUTE_TIMEOUT_SECONDS", "8"))
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = float(os.getenv("ADAMS_OVERPASS_TIMEOUT_SECONDS", "4"))
ENABLE_POI_SCORING = os.getenv("ADAMS_ROUTE_ENABLE_POI", "0") == "1"
POI_RADIUS_METRES = 500
POI_SAMPLE_POINTS = 5

# ─────────────────────────────────────────────────────────────
# POI tag map — this is the layer system.
# Each emotion maps to OpenStreetMap amenity/leisure tags.
# The backend counts how many of these exist near the route.
# Higher score = route better matches the driver's emotion.
# ─────────────────────────────────────────────────────────────

EMOTION_POI_TAGS: dict[str, list[str]] = {
    "relaxed": [
        "amenity=cafe",
        "leisure=park",
        "amenity=bench",
        "tourism=viewpoint",
        "natural=water",
    ],
    "happy": [
        "amenity=restaurant",
        "amenity=fast_food",
        "shop=mall",
        "leisure=playground",
        "tourism=attraction",
    ],
    "stressed": [
        # Stressed drivers benefit from fast, uninterrupted roads.
        # No POI targets — low POI density is the goal.
        # Score of 0 is intentionally good here.
    ],
    "tired": [
        "amenity=fuel",
        "amenity=rest_area",
        "highway=services",
    ],
    "focused": [
        # Minimal POIs — only coffee stops along route.
        "amenity=cafe",
    ],
    "neutral": [],
}

# For stressed/focused, fewer POIs = better.
# For all others, more matching POIs = better.
EMOTION_PREFERS_LOW_POI = {"stressed", "focused"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ROUTE_SERVER] %(levelname)s %(message)s",
)
logger = logging.getLogger("ROUTE_SERVER")


# ─────────────────────────────────────────────────────────────
# Coordinate helpers
# ─────────────────────────────────────────────────────────────

def _parse_lon_lat(value: str) -> tuple[float, float]:
    lon_text, lat_text = value.split(",", 1)
    return float(lon_text.strip()), float(lat_text.strip())


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "..."
    minutes = max(1, round(float(seconds) / 60))
    return f"{minutes} min"


def _sample_polyline(
    coordinates: list[list[float]],
    n: int = POI_SAMPLE_POINTS,
) -> list[tuple[float, float]]:
    """
    Pick n evenly-spaced points from the route polyline.
    coordinates are [lat, lon] pairs (already flipped from OSRM).
    Returns list of (lat, lon) tuples.
    """
    if not coordinates:
        return []
    total = len(coordinates)
    step  = max(1, total // n)
    return [(c[0], c[1]) for c in coordinates[::step][:n]]


# ─────────────────────────────────────────────────────────────
# Overpass POI scoring
# ─────────────────────────────────────────────────────────────

def _query_overpass(lat: float, lon: float, tags: list[str]) -> int:
    """
    Query Overpass for matching POIs within POI_RADIUS_METRES of (lat, lon).
    Returns the count of matching nodes.
    """
    tag_lines = "\n".join(
        f'  node["{t.split("=")[0]}"="{t.split("=")[1]}"]'
        f"(around:{POI_RADIUS_METRES},{lat},{lon});"
        for t in tags
    )
    query = f"[out:json][timeout:10];\n(\n{tag_lines}\n);\nout count;"

    try:
        body = urlencode({"data": query}).encode("utf-8")
        req = Request(
            OVERPASS_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent":   "ADAMS-Route-Server/1.0",
            },
            method="POST",
        )
        with urlopen(req, timeout=OVERPASS_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        elements = data.get("elements", [])
        if elements:
            return int(elements[0].get("tags", {}).get("total", 0))
        return 0

    except Exception as exc:
        logger.warning("Overpass query failed at (%.4f, %.4f): %s", lat, lon, exc)
        return 0


def fetch_poi_score(
    coordinates: list[list[float]],
    emotion: str,
) -> int:
    """
    Score a route by counting emotion-matched POIs near sampled points.

    For stressed/focused emotions, 0 is intentionally returned
    (fewer distractions = better, but we don't invert the score
    here — the Flutter tile already explains the route preference).
    """
    if not ENABLE_POI_SCORING:
        return 0

    tags = EMOTION_POI_TAGS.get(emotion, [])
    if not tags:
        return 0

    sample_points = _sample_polyline(coordinates, POI_SAMPLE_POINTS)
    if not sample_points:
        return 0

    total = 0
    for lat, lon in sample_points:
        total += _query_overpass(lat, lon, tags)

    logger.info(
        "POI score for %s: %d (sampled %d points, radius %dm)",
        emotion, total, len(sample_points), POI_RADIUS_METRES,
    )
    return total


# ─────────────────────────────────────────────────────────────
# Fallback route (when OSRM is unavailable)
# ─────────────────────────────────────────────────────────────

EMOTION_OFFSETS = {
    "relaxed":  0.010,
    "happy":    0.007,
    "stressed": 0.000,
    "tired":   -0.006,
    "focused":  0.003,
    "neutral":  0.000,
}

def _fallback_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    emotion: str,
    error: str | None = None,
) -> dict[str, Any]:
    lon1, lat1 = origin
    lon2, lat2 = destination
    offset  = EMOTION_OFFSETS.get(emotion, 0.0)
    mid_lon = (lon1 + lon2) / 2 + offset
    mid_lat = (lat1 + lat2) / 2 - offset

    response: dict[str, Any] = {
        "status":      "mock",
        "source":      "fallback",
        "emotion":     emotion,
        "duration":    "Mock min",
        "poi_score":   0,
        "coordinates": [
            [lat1, lon1],
            [mid_lat, mid_lon],
            [lat2, lon2],
        ],
    }
    if error:
        response["error"] = error
    return response


# ─────────────────────────────────────────────────────────────
# OSRM route fetch + POI scoring
# ─────────────────────────────────────────────────────────────

def _fetch_osrm_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
    emotion: str,
) -> dict[str, Any]:
    lon1, lat1 = origin
    lon2, lat2 = destination
    params = urlencode({"overview": "full", "geometries": "geojson"})
    url    = f"{OSRM_BASE_URL}/{lon1},{lat1};{lon2},{lat2}?{params}"
    req    = Request(url, headers={"User-Agent": "ADAMS-Route-Server/1.0"})

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        logger.warning("OSRM route failed, using fallback: %s", exc)
        return _fallback_route(origin, destination, emotion, str(exc))

    routes = data.get("routes") or []
    if data.get("code") != "Ok" or not routes:
        error = data.get("code", "No OSRM route returned")
        logger.warning("OSRM returned no route: %s", error)
        return _fallback_route(origin, destination, emotion, error)

    route           = routes[0]
    raw_coordinates = route.get("geometry", {}).get("coordinates", [])

    # OSRM returns [lon, lat] — flip to [lat, lon] for Flutter
    coordinates = [[lat, lon] for lon, lat in raw_coordinates]

    if not coordinates:
        return _fallback_route(origin, destination, emotion, "Route had no geometry")

    # ── POI scoring — the layer that connects emotion to map data ──
    poi_score = fetch_poi_score(coordinates, emotion)

    return {
        "status":      "mock",          # keeps Flutter parser happy
        "source":      "osrm",
        "emotion":     emotion,
        "distance_km": round(float(route.get("distance", 0)) / 1000, 1),
        "duration":    _format_duration(route.get("duration")),
        "poi_score":   poi_score,       # how many matching POIs near this route
        "coordinates": coordinates,
    }


# ─────────────────────────────────────────────────────────────
# Request builder
# ─────────────────────────────────────────────────────────────

def build_route(payload: dict[str, Any]) -> dict[str, Any]:
    origin_text      = str(payload.get("origin",      "")).strip()
    destination_text = str(payload.get("destination", "")).strip()
    emotion          = str(payload.get("emotion", "neutral")).strip().lower() or "neutral"

    if not origin_text or not destination_text:
        return {"status": "error", "error": "origin and destination are required"}

    try:
        origin      = _parse_lon_lat(origin_text)
        destination = _parse_lon_lat(destination_text)
    except (TypeError, ValueError) as exc:
        return {"status": "error", "error": f"Invalid coordinate format: {exc}"}

    if not all(math.isfinite(v) for v in (*origin, *destination)):
        return {"status": "error", "error": "Coordinates must be finite numbers"}

    return _fetch_osrm_route(origin, destination, emotion)


# ─────────────────────────────────────────────────────────────
# HTTP server  (unchanged from your working version)
# ─────────────────────────────────────────────────────────────

class RouteRequestHandler(BaseHTTPRequestHandler):
    server_version = "ADAMSRouteServer/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type",                  "application/json")
        self.send_header("Access-Control-Allow-Origin",   "*")
        self.send_header("Access-Control-Allow-Headers",  "Content-Type")
        self.send_header("Access-Control-Allow-Methods",  "GET, POST, OPTIONS")
        self.send_header("Content-Length",                str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"status": "ok"})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "healthy", "service": "ADAMS route server"})
            return
        self._send_json(404, {"status": "error", "error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/route":
            self._send_json(404, {"status": "error", "error": "Not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            raw_body = self.rfile.read(content_length)
            payload  = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._send_json(400, {"status": "error", "error": f"Invalid JSON: {exc}"})
            return

        response    = build_route(payload)
        status_code = 400 if response.get("status") == "error" else 200
        self._send_json(status_code, response)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RouteRequestHandler)
    logger.info("ADAMS route server running on http://%s:%s", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Route server stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
