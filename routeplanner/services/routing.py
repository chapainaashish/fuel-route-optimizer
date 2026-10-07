import requests
from django.conf import settings
from django.core.cache import cache

from routeplanner.exceptions import GeocodingError, RoutingError

ORS_BASE = "https://api.openrouteservice.org"
METERS_PER_MILE = 1609.344
GEOCODE_TTL = 60 * 60 * 24 * 30  # 30 days
ROUTE_TTL = 60 * 60 * 24  # 1 day
_session = requests.Session()  # Reusing TCP connection


def geocode_location(location) -> tuple[float, float]:
    """
    Accept a location and return (lat, lon).

    `location` may be:
      - the dict produced by LocationField:
          {"kind": "coords", "lat": .., "lon": ..}  -> returned as-is, no API call
          {"kind": "address", "query": "..."}       -> geocoded (1 API call, cached)
      - a plain address string
    """
    if isinstance(location, dict):
        if location.get("kind") == "coords":
            return location["lat"], location["lon"]
        query = location["query"]
    else:
        query = str(location)

    query = " ".join(query.split())
    cache_key = f"geo:{query.casefold()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        resp = _session.get(
            f"{ORS_BASE}/geocode/search",
            params={
                "api_key": settings.ORS_API_KEY,
                "text": query,
                "boundary.country": "US",
                "size": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f"Geocoding service failed: {exc}") from exc

    features = resp.json().get("features", [])
    if not features:
        raise GeocodingError(f"Could not find location: {query!r}")

    lon, lat = features[0]["geometry"]["coordinates"]
    result = (lat, lon)
    cache.set(cache_key, result, GEOCODE_TTL)
    return result


def get_route(start: tuple[float, float], finish: tuple[float, float]) -> dict:
    """
    Accept two (lat, lon) points and return route data (1 ORS API call, cached):

        {
            "geometry": [(lat, lon), ...],   # ordered points along the route
            "distance_miles": float,
            "duration_seconds": float,
        }
    """
    cache_key = "route:{:.4f},{:.4f}:{:.4f},{:.4f}".format(*start, *finish)
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        resp = _session.post(
            f"{ORS_BASE}/v2/directions/driving-car/geojson",
            headers={"Authorization": settings.ORS_API_KEY},
            json={
                "coordinates": [[start[1], start[0]], [finish[1], finish[0]]],
                "instructions": False,
            },
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RoutingError(f"Routing service failed: {exc}") from exc

    if resp.status_code != 200:
        raise RoutingError(f"ORS error {resp.status_code}: {resp.text[:200]}")

    feature = resp.json()["features"][0]
    summary = feature["properties"]["summary"]

    result = {
        "geometry": [(lat, lon) for lon, lat in feature["geometry"]["coordinates"]],
        "distance_miles": summary["distance"] / METERS_PER_MILE,
        "duration_seconds": summary["duration"],
    }
    cache.set(cache_key, result, ROUTE_TTL)
    return result
