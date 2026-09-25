"""Route risk, cold-chain, SAR, environment."""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Incident, Route, Sample, SensorReading, User, WeatherReading, iso, utcnow
from ..security import OPS, current_user, require_roles
from ..services import alerts, risk, sar, sync

router = APIRouter(prefix="/api", tags=["safety"], dependencies=[Depends(current_user)])


# ------------------------------------------------------------ route risk
class RiskIn(BaseModel):
    ice_pct: float = Field(ge=0, le=100)
    wind_kt: float = Field(ge=0, le=120)
    visibility_km: float = Field(ge=0, le=50)
    distance_km: float = Field(ge=0, le=5000)
    data_age_h: float = Field(ge=0, le=500)


@router.get("/risk/routes")
def risk_routes(db: Session = Depends(get_db)):
    return [risk.route_risk(db, r) for r in db.query(Route).order_by(Route.id).all()]


@router.post("/risk/score")
def risk_score(body: RiskIn):
    """What-if score from manual inputs (the sliders in the UI)."""
    return risk.compute(body.ice_pct, body.wind_kt, body.visibility_km, body.distance_km, body.data_age_h)


# ------------------------------------------------------------ cold-chain
class ReadingIn(BaseModel):
    temp_c: float = Field(ge=-90, le=40)
    ambient_c: Optional[float] = None


class DelayIn(BaseModel):
    hours: int = Field(4, ge=1, le=12)


@router.get("/coldchain")
def coldchain(db: Session = Depends(get_db)):
    out = []
    for s in db.query(Sample).order_by(Sample.id).all():
        a = alerts.cold_analysis(db, s)
        a.pop("series"), a.pop("forecast")
        out.append(a)
    return out


@router.get("/coldchain/{sid}")
def coldchain_one(sid: str, db: Session = Depends(get_db)):
    s = db.get(Sample, sid)
    if not s:
        raise HTTPException(404, "Unknown sample")
    return alerts.cold_analysis(db, s)


@router.post("/coldchain/{sid}/readings", status_code=201)
def add_reading(sid: str, body: ReadingIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["READING"]))):
    if not db.get(Sample, sid):
        raise HTTPException(404, "Unknown sample")
    res = sync.submit(db, user, "READING", sid, {"sample_id": sid, "temp_c": body.temp_c, "ambient_c": body.ambient_c})
    if res["status"] == "rejected":
        raise HTTPException(409, res["reason"])
    return alerts.cold_analysis(db, db.get(Sample, sid))


@router.post("/coldchain/{sid}/simulate-delay")
def simulate_delay(sid: str, body: DelayIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    """Demo tool: append `hours` of readings that continue the current trend (source='simulated')."""
    s = db.get(Sample, sid)
    if not s:
        raise HTTPException(404, "Unknown sample")
    a = alerts.cold_analysis(db, s)
    last = db.query(SensorReading).filter(SensorReading.sample_id == sid).order_by(SensorReading.at.desc()).first()
    rate = max(a["rate_c_per_h"] or 0.0, 0.8)
    for k in range(1, body.hours * 6 + 1):
        db.add(SensorReading(sample_id=sid, at=last.at + timedelta(minutes=10 * k), temp_c=round(a["current"] + rate * k / 6, 2), ambient_c=last.ambient_c, source="simulated"))
    db.commit()
    return alerts.cold_analysis(db, s)


@router.post("/coldchain/{sid}/reset-simulation")
def reset_simulation(sid: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    db.query(SensorReading).filter(SensorReading.sample_id == sid, SensorReading.source == "simulated").delete()
    db.commit()
    return alerts.cold_analysis(db, db.get(Sample, sid))


# ------------------------------------------------------------ SAR
class OpenIn(BaseModel):
    team: str


@router.get("/sar/status")
def sar_status(db: Session = Depends(get_db)):
    now = utcnow()
    inc = db.query(Incident).filter(Incident.state != "CLOSED").order_by(Incident.opened_at.desc()).first()
    return {"incident": sar.serialize(db, inc) if inc else None,
            "overdue": [{"team": t["team"], "overdue_min": t["overdue_min"], "lat": t["lat"], "lon": t["lon"]} for t in sar.overdue_teams(db, now)],
            "grace_min": sar.GRACE_MIN}


@router.get("/sar/incidents")
def incidents(db: Session = Depends(get_db)):
    return [sar.serialize(db, i) for i in db.query(Incident).order_by(Incident.opened_at.desc()).limit(50).all()]


@router.post("/sar/scenario", status_code=201)
def scenario(db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    inc = sar.simulate_missed_checkin(db, "Bravo", user.username)
    db.commit()
    return sar.serialize(db, inc)


@router.post("/sar/reset")
def sar_reset(db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    sar.reset_scenario(db, user.username)
    db.commit()
    return {"ok": True}


@router.post("/sar/incidents", status_code=201)
def open_incident(body: OpenIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    overdue = {t["team"]: t for t in sar.overdue_teams(db)}
    if body.team not in overdue:
        raise HTTPException(409, f"Team {body.team} is not overdue")
    inc = sar.open_incident(db, body.team, user.username)
    db.commit()
    return sar.serialize(db, inc)


@router.post("/sar/incidents/{iid}/close")
def close_incident(iid: str, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    inc = db.get(Incident, iid)
    if not inc:
        raise HTTPException(404, "Unknown incident")
    inc.state, inc.closed_at = "CLOSED", utcnow()
    from ..audit import audit
    audit(db, user.username, "incident_close", "incident", iid)
    db.commit()
    return sar.serialize(db, inc)


# ------------------------------------------------------------ environment
@router.get("/env/weather")
def weather(station: str = "Bharati", hours: int = Query(48, ge=1, le=168), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(hours=hours)
    rows = db.query(WeatherReading).filter(WeatherReading.station == station, WeatherReading.at >= since).order_by(WeatherReading.at).all()
    ser = [{"at": iso(r.at), "temp_c": r.temp_c, "wind_kt": r.wind_kt, "gust_kt": r.gust_kt, "wind_dir": r.wind_dir, "vis_km": r.vis_km, "pressure_hpa": r.pressure_hpa} for r in rows]
    return {"station": station, "latest": ser[-1] if ser else None, "series": ser, "synthetic": True}
