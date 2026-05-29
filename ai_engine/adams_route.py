"""
ADAMS Route
===========
Navigation helper for the Advanced Driver Alertness Monitoring System.

Fix vs 1.0:
  - Overpass API 406 error fixed: must send request as form data with
    correct Content-Type header, not as a params dict.
  - Added User-Agent header (required by Overpass public instance).
  - Graceful fallback: if Overpass fails, returns a plain spoken string
    instead of crashing the pipeline.

Authors : ADAMS Team
Version : 1.1.0
"""

import math
import logging
import requests
from typing import Optional

logger = logging.getLogger("adams.route")

_OSRM_BASE     = "https://router.project-osrm.org/route/v1/driving"
_OVERPASS_BASE = "https://overpass-api.de/api/interpreter"
_TIMEOUT       = 8

# Overpass requires a User-Agent header or it returns 406
_HEADERS = {
    "User-Agent":   "ADAMS-Driver-Assistant/1.1 (educational project)",
    "Content-Type": "application/x-www-form-urlencoded",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict:
    """
    Fetch a driving route between two (lon, lat) coordinates via OSRM.

    Returns dict with: ok, distance_km, duration_min, steps, raw
    """
    lon1, lat1 = origin
    lon2, lat2 = destination
    url = f"{_OSRM_BASE}/{lon1},{lat1};{lon2},{lat2}"

    try:
        resp = requests.get(
            url,
            params={"overview": "false", "steps": "true"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            logger.warning("OSRM returned no routes: %s", data.get("code"))
            return {"ok": False, "error": data.get("code", "no route")}

        route    = data["routes"][0]
        distance = route["distance"] / 1000
        duration = route["duration"] / 60

        return {
            "ok":           True,
            "distance_km":  round(distance, 1),
            "duration_min": round(duration, 1),
            "steps":        _extract_steps(route),
            "raw":          data,
        }

    except requests.RequestException as exc:
        logger.error("OSRM request failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def find_rest_stop(lat: float, lon: float, radius_m: int = 5000) -> Optional[dict]:
    """Find the nearest fuel station / rest area via Overpass API."""
    return _overpass_poi(
        lat, lon, radius_m,
        query=(
            f'node["amenity"~"fuel|rest_area|service_area"]'
            f"(around:{radius_m},{lat},{lon});"
            f'way["amenity"~"fuel|rest_area|service_area"]'
            f"(around:{radius_m},{lat},{lon});"
        ),
        label="rest stop",
    )


def find_scenic_point(lat: float, lon: float, radius_m: int = 8000) -> Optional[dict]:
    """Find a nearby viewpoint or park via Overpass API."""
    return _overpass_poi(
        lat, lon, radius_m,
        query=(
            f'node["tourism"~"viewpoint|picnic_site"]'
            f"(around:{radius_m},{lat},{lon});"
            f'node["leisure"="park"]'
            f"(around:{radius_m},{lat},{lon});"
        ),
        label="scenic point",
    )


def route_summary_for_adams(
    suggested_route: str,
    origin: tuple,
    destination: tuple,
) -> str:
    """
    Convert AdamsBrain's suggested_route into a spoken sentence.
    Always returns a usable string — never raises.
    """
    try:
        if suggested_route == "FASTEST":
            info = get_route(origin, destination)
            if info["ok"]:
                return (
                    f"Taking the fastest route. "
                    f"About {info['duration_min']} minutes, "
                    f"{info['distance_km']} kilometres."
                )
            return "Taking the fastest route to your destination."

        if suggested_route == "REST_STOP":
            lat, lon = origin[1], origin[0]
            poi = find_rest_stop(lat, lon)
            if poi:
                return (
                    f"There's a rest stop nearby — {poi['name']} — "
                    f"about {poi.get('distance_m', '?')} metres away. "
                    f"I strongly recommend we pull in."
                )
            return "The nearest rest stop is just ahead. Please consider pulling over soon."

        if suggested_route == "SCENIC":
            lat, lon = origin[1], origin[0]
            poi = find_scenic_point(lat, lon)
            if poi:
                return (
                    f"There's a scenic area nearby — {poi['name']}. "
                    f"A short break there might help you relax."
                )
            return "Taking a calm scenic detour. This should help you de-stress."

    except Exception as exc:
        logger.error("route_summary_for_adams failed: %s", exc)

    return ""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_steps(route: dict) -> list[str]:
    steps = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            maneuver      = step.get("maneuver", {})
            maneuver_type = maneuver.get("type", "")
            modifier      = maneuver.get("modifier", "")
            name          = step.get("name", "")
            distance      = round(step.get("distance", 0))

            if maneuver_type == "arrive":
                steps.append("Arrive at your destination.")
            elif name:
                direction = f"{maneuver_type} {modifier}".strip()
                steps.append(f"In {distance} m, {direction} onto {name}.")
    return steps


def _overpass_poi(
    lat: float,
    lon: float,
    radius_m: int,
    query: str,
    label: str,
) -> Optional[dict]:
    """
    Run an Overpass QL query and return the nearest result.

    Fix: POST with application/x-www-form-urlencoded + User-Agent header
    to avoid 406 Not Acceptable from the public Overpass instance.
    """
    full_query = f"[out:json][timeout:10];\n(\n{query}\n);\nout center 5;"

    try:
        resp = requests.post(
            _OVERPASS_BASE,
            data=f"data={requests.utils.quote(full_query)}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])

        if not elements:
            logger.debug("No %s found within %dm.", label, radius_m)
            return None

        el   = elements[0]
        name = el.get("tags", {}).get("name", label.title())
        plat = el.get("lat") or el.get("center", {}).get("lat", lat)
        plon = el.get("lon") or el.get("center", {}).get("lon", lon)

        dlat = (plat - lat) * 111_000
        dlon = (plon - lon) * 111_000 * math.cos(math.radians(lat))
        dist = int(math.sqrt(dlat ** 2 + dlon ** 2))

        return {"name": name, "lat": plat, "lon": plon, "distance_m": dist}

    except Exception as exc:
        logger.error("Overpass query failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    SEOUL   = (126.9780, 37.5665)
    GANGNAM = (127.0276, 37.4979)

    print("── Fastest Route ──────────────────────────────────")
    r = get_route(SEOUL, GANGNAM)
    if r["ok"]:
        print(f"  {r['distance_km']} km | {r['duration_min']} min")
        for step in r["steps"][:3]:
            print(f"  → {step}")
    else:
        print("  Error:", r.get("error"))

    print("\n── REST_STOP summary ──────────────────────────────")
    print(" ", route_summary_for_adams("REST_STOP", SEOUL, GANGNAM))

    print("\n── SCENIC summary ─────────────────────────────────")
    print(" ", route_summary_for_adams("SCENIC", SEOUL, GANGNAM))