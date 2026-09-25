"""Geometry helpers: polar stereographic projection, distances, land mask and the
demo sea-ice layer.

The coastline comes from Natural Earth (real). The sea-ice concentration is a
SYNTHETIC field derived from distance to the coast; it exists so the route-risk
and map features run end to end. Swap `sea_ice()` for a sampler of NSIDC /
Copernicus data when you have that data (see docs/DATA.md).
"""
import json
import math
from functools import lru_cache

import numpy as np
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform, unary_union
from shapely.prepared import prep

from ..config import settings

S = 1000.0
KM_PER_UNIT = 6.371            # 1 projected unit = 6.371 km (scale 2 * S * tan(...))
EARTH_KM = 6371.0088


def proj(lat: float, lon: float):
    """South polar stereographic, 0 deg meridian up (svg y axis points down)."""
    r = 2 * S * math.tan(math.pi / 4 + math.radians(lat) / 2)
    l = math.radians(lon)
    return r * math.sin(l), -r * math.cos(l)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def offset_km(lat: float, lon: float, north_km: float, east_km: float):
    dlat = north_km / 111.195
    dlon = east_km / (111.195 * max(0.05, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def destination(lat: float, lon: float, bearing_deg: float, dist_km: float):
    b = math.radians(bearing_deg)
    return offset_km(lat, lon, dist_km * math.cos(b), dist_km * math.sin(b))


def route_length_km(waypoints) -> float:
    return sum(haversine_km(a[0], a[1], b[0], b[1]) for a, b in zip(waypoints, waypoints[1:]))


def sample_route(waypoints, n: int = 25):
    """n points spaced evenly (by distance) along the polyline."""
    segs = [(a, b, haversine_km(a[0], a[1], b[0], b[1])) for a, b in zip(waypoints, waypoints[1:])]
    total = sum(s[2] for s in segs) or 1e-9
    out = []
    for i in range(n):
        d = total * i / (n - 1)
        for a, b, L in segs:
            if d <= L or (a, b, L) == segs[-1]:
                f = 0 if L == 0 else min(1, d / L)
                out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
                break
            d -= L
    return out


# ---------------------------------------------------------------- land / ice
def _proj_xy(x, y, z=None):
    lon, lat = np.radians(np.asarray(x, dtype=float)), np.radians(np.asarray(y, dtype=float))
    r = 2 * S * np.tan(np.pi / 4 + lat / 2)
    return r * np.sin(lon), -r * np.cos(lon)


@lru_cache(maxsize=1)
def _land():
    gj = json.loads((settings.data_dir / "geo" / "coastline.geojson").read_text())
    u = unary_union([shape(f["geometry"]) for f in gj["features"]])
    return u, prep(u), transform(_proj_xy, u)


def is_ocean(lat: float, lon: float) -> bool:
    _, prepared, _ = _land()
    return not prepared.contains(Point(lon, lat))


def distance_to_coast_km(lat: float, lon: float) -> float:
    _, _, projected = _land()
    x, y = proj(lat, lon)
    return projected.boundary.distance(Point(x, y)) * KM_PER_UNIT


def sea_ice(lat: float, lon: float):
    """Synthetic sea-ice concentration in percent, None over land or ice shelf."""
    if not is_ocean(lat, lon):
        return None
    d = distance_to_coast_km(lat, lon)
    base = 10 + 86 * math.exp(-d / 230.0)
    wobble = 1 + 0.12 * math.sin(lon * 0.35) * math.cos(lat * 1.3)
    return round(max(3.0, min(99.0, base * wobble)), 1)


@lru_cache(maxsize=1)
def seaice_geojson() -> dict:
    feats, lat = [], -71.0
    while lat < -58.0:
        lon = 0.0
        while lon < 105.0:
            c = sea_ice(lat + 0.375, lon + 1.25)
            if c is not None and c >= 5:
                ring = [[lon, lat], [lon + 2.5, lat], [lon + 2.5, lat + 0.75], [lon, lat + 0.75], [lon, lat]]
                feats.append({"type": "Feature", "properties": {"c": int(round(c))}, "geometry": {"type": "Polygon", "coordinates": [ring]}})
            lon += 2.5
        lat += 0.75
    return {"type": "FeatureCollection", "features": feats,
            "properties": {"synthetic": True, "note": "Synthetic sea-ice concentration (demo). Replace with NSIDC / Copernicus data."}}


def load_geojson(name: str) -> dict:
    return json.loads((settings.data_dir / "geo" / f"{name}.geojson").read_text())
