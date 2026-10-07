import math

import numpy as np
from scipy.spatial import cKDTree

from ..models import FuelStation

EARTH_RADIUS_MILES = 3958.8
DEFAULT_RADIUS_MILES = 10.0
ROUTE_SAMPLE_STEP_MILES = 0.25


def _to_xyz(lat_deg, lon_deg) -> np.ndarray:
    """lat/lon (degrees) -> 3D coordinates in miles on a sphere. Shape (N, 3)."""
    lat = np.radians(np.asarray(lat_deg, dtype=float))
    lon = np.radians(np.asarray(lon_deg, dtype=float))
    c = np.cos(lat)
    return EARTH_RADIUS_MILES * np.column_stack(
        [c * np.cos(lon), c * np.sin(lon), np.sin(lat)]
    )


def _cumulative_miles(points: np.ndarray) -> np.ndarray:
    """Haversine cumulative distance along the route. points: (N, 2) [lat, lon]."""
    lat = np.radians(points[:, 0])
    lon = np.radians(points[:, 1])
    dlat, dlon = np.diff(lat), np.diff(lon)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon / 2) ** 2
    )
    seg = 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))
    return np.concatenate([[0.0], np.cumsum(seg)])


def _resample_route(points, cum, step_miles):
    """Evenly spaced points along the route and their mile markers."""
    total = cum[-1]
    n = max(int(math.ceil(total / step_miles)), 1)
    markers = np.linspace(0.0, total, n + 1)
    lat = np.interp(markers, cum, points[:, 0])
    lon = np.interp(markers, cum, points[:, 1])
    return np.column_stack([lat, lon]), markers


def _bbox_candidates(points: np.ndarray, radius_miles: float):
    """Cheap DB prefilter: route bounding box padded by radius."""
    lat_pad = math.degrees(radius_miles / EARTH_RADIUS_MILES)
    max_abs_lat = min(89.0, float(np.max(np.abs(points[:, 0]))) + 1.0)
    lon_pad = lat_pad / math.cos(math.radians(max_abs_lat))

    return FuelStation.objects.filter(
        lat__gte=float(points[:, 0].min()) - lat_pad,
        lat__lte=float(points[:, 0].max()) + lat_pad,
        lon__gte=float(points[:, 1].min()) - lon_pad,
        lon__lte=float(points[:, 1].max()) + lon_pad,
    )


def stations_near_route(
    geometry,
    route_distance_miles: float | None = None,
    radius_miles: float = DEFAULT_RADIUS_MILES,
):
    """
    Return stations within `radius_miles` of the route, sorted by mile marker.

    Each item: {"station": FuelStation, "distance_to_route_miles": float,
                "mile_marker": float}
    """
    points = np.asarray(geometry, dtype=float)
    if len(points) < 2:
        return []

    cum = _cumulative_miles(points)
    if cum[-1] <= 0:
        return []
    # Rescale so the last point equals the router's reported distance.
    if route_distance_miles:
        cum = cum * (route_distance_miles / cum[-1])

    candidates = list(_bbox_candidates(points, radius_miles))
    if not candidates:
        return []

    # KD-tree over densified route points
    sampled, sample_markers = _resample_route(points, cum, ROUTE_SAMPLE_STEP_MILES)
    tree = cKDTree(_to_xyz(sampled[:, 0], sampled[:, 1]))

    station_xyz = _to_xyz(
        [s.lat for s in candidates],
        [s.lon for s in candidates],
    )

    # Nearest route point per station; stations beyond the radius come back as inf.
    dist, idx = tree.query(station_xyz, k=1, distance_upper_bound=radius_miles)

    results = [
        {
            "station": candidates[i],
            "distance_to_route_miles": float(dist[i]),
            "mile_marker": float(sample_markers[idx[i]]),
        }
        for i in np.flatnonzero(np.isfinite(dist))
    ]
    results.sort(key=lambda r: r["mile_marker"])
    return results
