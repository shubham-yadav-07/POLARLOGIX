"""Emergency / SAR workflow.

State machine (each step is written to incident_actions with a timestamp):
  1 timer running -> 2 timer expired -> 3 other evidence checked -> 4 incident created
  -> 5 weather attached -> 6 nearest resources -> 7 search grid -> 8 response dispatched

The search grid is a SIMULATION: a gaussian probability field around the last
known position, shifted downwind, whose spread grows with time since last
contact. It is NOT a leeway / SAROPS model and must not be used operationally.
"""
import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..audit import audit
from ..models import Asset, Checkin, Incident, IncidentAction, Personnel, iso, utcnow
from . import geo, risk

GRACE_MIN = 30
DRIFT_KM_PER_KT_H = 0.05        # heuristic
SIGMA_BASE_KM, SIGMA_PER_H_KM = 0.8, 0.6
CELL_KM, ROWS, COLS = 1.2, 4, 6


def _team_rows(db: Session):
    teams = {}
    for p in db.query(Personnel).all():
        teams.setdefault(p.team, []).append(p)
    return teams


def team_state(members, now: datetime) -> dict:
    last = max(m.last_checkin_at for m in members)
    due = max(m.next_due_at for m in members)
    lead = max(members, key=lambda m: m.last_checkin_at)
    return {"team": members[0].team, "members": len(members), "last_checkin_at": last, "next_due_at": due,
            "overdue_min": max(0, int((now - due).total_seconds() / 60)), "lat": lead.lat, "lon": lead.lon,
            "interval": members[0].checkin_interval_min, "hold": any(m.hold for m in members)}


def overdue_teams(db: Session, now: Optional[datetime] = None, grace_min: int = 0) -> list:
    now = now or utcnow()
    out = []
    for members in _team_rows(db).values():
        st = team_state(members, now)
        if now > st["next_due_at"] + timedelta(minutes=grace_min):
            out.append(st)
    return sorted(out, key=lambda s: -s["overdue_min"])


def search_grid(lat: float, lon: float, wind_from_deg: float, wind_kt: float, elapsed_min: float) -> dict:
    elapsed_h = max(elapsed_min, 30) / 60
    drift_to = (wind_from_deg + 180) % 360
    shift = DRIFT_KM_PER_KT_H * wind_kt * elapsed_h
    clat, clon = geo.destination(lat, lon, drift_to, shift)
    sigma = SIGMA_BASE_KM + SIGMA_PER_H_KM * elapsed_h
    cells, total = [], 0.0
    for r in range(ROWS):
        for c in range(COLS):
            north = ((ROWS - 1) / 2 - r) * CELL_KM
            east = (c - (COLS - 1) / 2) * CELL_KM
            w = math.exp(-((north ** 2 + east ** 2) / (2 * sigma ** 2)))
            la0, lo0 = geo.offset_km(clat, clon, north - CELL_KM / 2, east - CELL_KM / 2)
            la1, lo1 = geo.offset_km(clat, clon, north + CELL_KM / 2, east + CELL_KM / 2)
            cells.append({"row": r, "col": c, "lat0": round(la0, 5), "lat1": round(la1, 5), "lon0": round(lo0, 5), "lon1": round(lo1, 5), "w": w})
            total += w
    for cell in cells:
        cell["p"] = round(cell.pop("w") / total, 4)
    return {"center": [round(clat, 5), round(clon, 5)], "shift_km": round(shift, 2), "drift_to_deg": round(drift_to),
            "sigma_km": round(sigma, 2), "cell_km": CELL_KM, "cells": cells,
            "note": "Simulation (gaussian, wind-shifted). Not a leeway or SAROPS model."}


def _nearest_resources(db: Session, lat: float, lon: float, n: int = 3) -> list:
    rows = db.query(Asset).filter(Asset.type.in_(["Snowcat", "UAV"]), Asset.status.in_(["Available", "In use"])).all()
    rows = sorted(rows, key=lambda a: geo.haversine_km(lat, lon, a.lat, a.lon))[:n]
    return [{"id": a.id, "type": a.type, "status": a.status, "km": round(geo.haversine_km(lat, lon, a.lat, a.lon), 1)} for a in rows]


def open_incident(db: Session, team: str, username: str = "system", now: Optional[datetime] = None) -> Incident:
    now = now or utcnow()
    existing = db.query(Incident).filter(Incident.team == team, Incident.state != "CLOSED").first()
    if existing:
        return existing
    members = [m for m in db.query(Personnel).filter(Personnel.team == team).all()]
    if not members:
        raise ValueError(f"Unknown team {team}")
    st = team_state(members, now)
    seq = db.query(Incident).count() + 1
    inc = Incident(id=f"SAR-{now.year}-{seq:02d}", team=team, state="OPEN", severity="high", opened_at=now,
                   last_lat=st["lat"], last_lon=st["lon"], overdue_min=st["overdue_min"])
    wx = risk.latest_weather(db, "Bharati")
    inc.weather = None if wx is None else {"wind_kt": wx.wind_kt, "gust_kt": wx.gust_kt, "wind_dir": wx.wind_dir, "vis_km": wx.vis_km, "temp_c": wx.temp_c}
    inc.resources = _nearest_resources(db, st["lat"], st["lon"])
    elapsed = st["overdue_min"] + st["interval"]
    inc.grid = search_grid(st["lat"], st["lon"], wx.wind_dir if wx else 90, wx.wind_kt if wx else 15, elapsed)
    db.add(inc)
    db.flush()

    later = db.query(Checkin).filter(Checkin.team == team, Checkin.at > st["last_checkin_at"]).count()
    res = ", ".join(f"{r['id']} ({r['km']} km)" for r in inc.resources[:2]) or "none found"
    steps = [
        ("Check-in timer running", f"Team {team}, interval {st['interval']} min, {st['members']} people", st["last_checkin_at"]),
        ("Timer expired", f"No confirmation for {st['overdue_min']} min, warning created", st["next_due_at"]),
        ("Other evidence checked", f"{later} later check-ins on record; no beacon or radio contact logged", now),
        (f"Incident {inc.id} created", f"Severity high, last position {st['lat']:.3f}, {st['lon']:.3f}", now),
        ("Weather attached", ("Wind %.0f kt from %d, visibility %.1f km, %.1f C" % (wx.wind_kt, wx.wind_dir, wx.vis_km, wx.temp_c)) if wx else "No weather on record", now),
        ("Nearest resources listed", res, now),
        ("Search grid generated", f"{len(inc.grid['cells'])} cells, shifted {inc.grid['shift_km']} km downwind, probability weighted (simulation)", now),
        ("Response dispatched", "Nearest UAV tasked, rescue team notified. Recorded only: this prototype does not contact anyone.", now),
    ]
    for i, (title, detail, at) in enumerate(steps, 1):
        db.add(IncidentAction(incident_id=inc.id, step_no=i, title=title, detail=detail[:300], at=at if i <= 2 else now + timedelta(seconds=i)))
    inc.state = "DISPATCHED"
    audit(db, username, "incident_open", "incident", inc.id, {"team": team, "overdue_min": st["overdue_min"]})
    return inc


def simulate_missed_checkin(db: Session, team: str = "Bravo", username: str = "system") -> Incident:
    """Demo helper: make the team 35 minutes overdue and open an incident."""
    now = utcnow()
    for m in db.query(Personnel).filter(Personnel.team == team).all():
        m.next_due_at = now - timedelta(minutes=35)
        m.last_checkin_at = m.next_due_at - timedelta(minutes=m.checkin_interval_min)
        m.hold = True
    audit(db, username, "scenario_missed_checkin", "team", team)
    db.flush()
    return open_incident(db, team, username, now)


def reset_scenario(db: Session, username: str = "system") -> None:
    now = utcnow()
    for inc in db.query(Incident).filter(Incident.state != "CLOSED").all():
        inc.state, inc.closed_at = "CLOSED", now
    for m in db.query(Personnel).all():
        if m.hold or m.next_due_at < now:
            m.hold = False
            m.last_checkin_at = now - timedelta(minutes=max(10, m.checkin_interval_min - 10))
            m.next_due_at = m.last_checkin_at + timedelta(minutes=m.checkin_interval_min)
    audit(db, username, "scenario_reset", "team", "*")


def serialize(db: Session, inc: Incident) -> dict:
    acts = db.query(IncidentAction).filter(IncidentAction.incident_id == inc.id).order_by(IncidentAction.step_no, IncidentAction.id).all()
    return {"id": inc.id, "team": inc.team, "state": inc.state, "severity": inc.severity, "opened_at": iso(inc.opened_at),
            "closed_at": iso(inc.closed_at), "last": [inc.last_lat, inc.last_lon], "overdue_min": inc.overdue_min,
            "weather": inc.weather, "resources": inc.resources, "grid": inc.grid,
            "actions": [{"step": a.step_no, "title": a.title, "detail": a.detail, "at": iso(a.at)} for a in acts]}
