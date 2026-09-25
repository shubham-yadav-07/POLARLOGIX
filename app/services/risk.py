"""Explainable route-risk score.

score = 0.35*ice + 0.25*wind + 0.15*visibility + 0.10*distance + 0.15*data_age
Every input is normalised to 0..1 first. The weights are PROTOTYPE values chosen
for explainability; they are not validated against real incident data.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import EnvLayer, Route, WeatherReading, utcnow
from . import geo

WEIGHTS = {"ice": 0.35, "wind": 0.25, "visibility": 0.15, "distance": 0.10, "data_age": 0.15}
LABELS = {"ice": "Sea ice", "wind": "Wind", "visibility": "Visibility", "distance": "Distance", "data_age": "Data age"}


def normalise(ice_pct: float, wind_kt: float, vis_km: float, distance_km: float, data_age_h: float) -> dict:
    clamp = lambda x: max(0.0, min(1.0, x))
    return {"ice": clamp(ice_pct / 100), "wind": clamp(wind_kt / 50), "visibility": clamp(1 - vis_km / 15),
            "distance": clamp(distance_km / 600), "data_age": clamp(data_age_h / 72)}


def compute(ice_pct, wind_kt, vis_km, distance_km, data_age_h) -> dict:
    raw = {"ice": ice_pct, "wind": wind_kt, "visibility": vis_km, "distance": distance_km, "data_age": data_age_h}
    units = {"ice": "%", "wind": "kt", "visibility": "km", "distance": "km", "data_age": "h"}
    norm = normalise(ice_pct, wind_kt, vis_km, distance_km, data_age_h)
    parts = [{"key": k, "label": LABELS[k], "raw": round(raw[k], 1), "unit": units[k], "value": round(norm[k], 3),
              "weight": WEIGHTS[k], "contribution": round(norm[k] * WEIGHTS[k], 3)} for k in WEIGHTS]
    score = round(sum(p["contribution"] for p in parts), 3)
    band = "LOW" if score < 0.33 else "MODERATE" if score < 0.66 else "HIGH"
    top = max(parts, key=lambda p: p["contribution"])
    why = f"{top['label']} adds the most ({top['contribution']:.2f} of {score:.2f})."
    if norm["data_age"] > 0.5:
        why += f" Inputs are {data_age_h:.0f} h old, so treat the score with caution."
    return {"score": score, "band": band, "parts": parts, "why": why}


def latest_weather(db: Session, station: str = "Bharati") -> Optional[WeatherReading]:
    return db.query(WeatherReading).filter(WeatherReading.station == station).order_by(WeatherReading.at.desc()).first()


def route_risk(db: Session, route: Route, station: str = "Bharati") -> dict:
    wx = latest_weather(db, station)
    layer = db.get(EnvLayer, "seaice")
    pts = geo.sample_route(route.waypoints, 25)
    ice_vals = [c for c in (geo.sea_ice(la, lo) for la, lo in pts) if c is not None]
    ice = sum(ice_vals) / len(ice_vals) if ice_vals else 0.0
    now = utcnow()
    age = max((now - wx.at).total_seconds() / 3600 if wx else 72,
              (now - layer.updated_at).total_seconds() / 3600 if layer else 72)
    dist = geo.route_length_km(route.waypoints)
    res = compute(ice, wx.wind_kt if wx else 30, wx.vis_km if wx else 5, dist, age)
    res.update({"route_id": route.id, "name": route.name, "kind": route.kind, "distance_km": round(dist, 0),
                "ice_max_pct": round(max(ice_vals), 0) if ice_vals else 0, "ocean_points": len(ice_vals),
                "note": "" if ice_vals else "This route is over land or ice shelf: no sea-ice on the path.",
                "inputs": "Sea ice: synthetic demo layer. Weather: latest reading at " + station + "."})
    return res
