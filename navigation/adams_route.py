"""
ADAMS Route
===========
Navigation helper for the Advanced Driver Alertness Monitoring System.

Wraps the free OSRM (Open Source Routing Machine) API to translate
AdamsBrain's suggested_route values into real turn-by-turn directions
and nearby POI lookups (rest stops, scenic routes).

No API key required — uses the public OSRM demo server.
For production, host your own OSRM instance or swap the base URL.

Authors : ADAMS Team
Version : 1.0.0
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger("adams.route")

# Public OSRM demo server (driving profile)
_OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"

# Overpass API — finds real rest stops / scenic viewpoints near a point
_OVERPASS_BASE = "https://overpass-api.de/api/interpreter"

# Timeout for all external HTTP calls
_TIMEOUT = 8


# ---------------------------------------------------------------------------
# Main helpers
# ---------------------------------------------------------------------------

def get_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict:
    """
    Fetch a driving route between two coordinates.

    Parameters
    ----------
    origin : (longitude, latitude)
    destination : (longitude, latitude)

    Returns
    -------
    dict with keys:
      ok          – bool, False on any error
      distance_km – float
      duration_min– float
      steps       – list of instruction strings
      raw         – full OSRM JSON (for debugging)
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
        distance = route["distance"] / 1000          # metres → km
        duration = route["duration"] / 60            # seconds → minutes
        steps    = _extract_steps(route)

        return {
            "ok":           True,
            "distance_km":  round(distance, 1),
            "duration_min": round(duration, 1),
            "steps":        steps,
            "raw":          data,
        }

    except requests.RequestException as exc:
        logger.error("OSRM request failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def find_rest_stop(lat: float, lon: float, radius_m: int = 5000) -> Optional[dict]:
    """
    Find the nearest motorway rest stop / service area via Overpass API.

    Returns a dict with name, lat, lon, distance_m — or None if not found.
    """
    return _overpass_poi(
        lat, lon, radius_m,
        query=f"""
        node["amenity"~"fuel|rest_area|service"](around:{radius_m},{lat},{lon});
        way["amenity"~"fuel|rest_area|service"](around:{radius_m},{lat},{lon});
        """,
        label="rest stop",
    )


def find_scenic_point(lat: float, lon: float, radius_m: int = 8000) -> Optional[dict]:
    """
    Find a nearby viewpoint or scenic area via Overpass API.

    Returns a dict with name, lat, lon — or None if not found.
    """
    return _overpass_poi(
        lat, lon, radius_m,
        query=f"""
        node["tourism"~"viewpoint|picnic_site|park"](around:{radius_m},{lat},{lon});
        """,
        label="scenic point",
    )


def route_summary_for_adams(suggested_route: str, origin: tuple, destination: tuple) -> str:
    """
    Convert AdamsBrain's suggested_route string into a spoken sentence.

    Parameters
    ----------
    suggested_route : "FASTEST" | "SCENIC" | "REST_STOP"
    origin          : (lon, lat) of current position
    destination     : (lon, lat) of final destination

    Returns
    -------
    str — a short sentence ready for AdamsVoice.speak()
    """
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
        return "I'm looking for the nearest rest stop. Please consider pulling over soon."

    if suggested_route == "SCENIC":
        lat, lon = origin[1], origin[0]
        poi = find_scenic_point(lat, lon)
        if poi:
            return (
                f"There's a scenic area ahead — {poi['name']}. "
                f"A calm detour might help you relax."
            )
        return "Taking a calm scenic route. This should help you de-stress."

    return "Route information unavailable."


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_steps(route: dict) -> list[str]:
    """Pull human-readable step instructions out of an OSRM route."""
    steps = []
    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            maneuver_type = maneuver.get("type", "")
            modifier     = maneuver.get("modifier", "")
            name         = step.get("name", "")
            distance     = round(step.get("distance", 0))

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
    """Run an Overpass QL query and return the nearest result."""
    full_query = f"[out:json][timeout:10];\n({query}\n);\nout center 5;"
    try:
        resp = requests.post(
            _OVERPASS_BASE,
            data={"data": full_query},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])

        if not elements:
            logger.debug("No %s found within %dm.", label, radius_m)
            return None

        # Pick the first result (Overpass returns nearest first with `out center`)
        el   = elements[0]
        name = el.get("tags", {}).get("name", label.title())
        plat = el.get("lat") or el.get("center", {}).get("lat", lat)
        plon = el.get("lon") or el.get("center", {}).get("lon", lon)

        # Rough distance in metres (good enough for spoken output)
        import math
        dlat = (plat - lat) * 111_000
        dlon = (plon - lon) * 111_000 * math.cos(math.radians(lat))
        dist = int(math.sqrt(dlat ** 2 + dlon ** 2))

        return {"name": name, "lat": plat, "lon": plon, "distance_m": dist}

    except Exception as exc:
        logger.error("Overpass query failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    SEOUL    = (126.9780, 37.5665)   # lon, lat
    GANGNAM  = (127.0276, 37.4979)

    print("── Fastest Route ─────────────────────────────────")
    r = get_route(SEOUL, GANGNAM)
    if r["ok"]:
        print(f"  {r['distance_km']} km  |  {r['duration_min']} min")
        for step in r["steps"][:4]:
            print(f"  → {step}")
    else:
        print("  Error:", r["error"])

    print("\n── Route Summary (REST_STOP) ─────────────────────")
    print(" ", route_summary_for_adams("REST_STOP", SEOUL, GANGNAM))

    print("\n── Route Summary (SCENIC) ────────────────────────")
    print(" ", route_summary_for_adams("SCENIC", SEOUL, GANGNAM))