"""Dashboard, geo layers, sync API, assistant, reports."""
import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (Asset, AuditLog, CargoHandoff, Incident, InventoryItem, Mission, Personnel, Route, Sample, Station, SyncConflict, SyncEvent, User,
                      WeatherReading, iso, utcnow)
from ..security import OPS, current_user, require_roles
from ..serializers import person_dict
from ..services import alerts, assistant, geo, inventory as inv_svc, risk, sar, sync
from ..services.sync import Ev

router = APIRouter(prefix="/api", tags=["platform"], dependencies=[Depends(current_user)])


# ------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    al = alerts.compute(db, now)
    items = db.query(InventoryItem).all()
    by = {i.id: i for i in items}
    wx = risk.latest_weather(db, "Bharati")
    sample = db.query(Sample).order_by(Sample.id).first()
    cold = alerts.cold_analysis(db, sample) if sample else None
    if cold:
        cold.pop("series"), cold.pop("forecast")
    bulk, trav = by.get("INV-DIESEL-S"), by.get("INV-DIESEL-T")
    from ..models import CargoItem
    return {
        "kpi": {"active_missions": db.query(Mission).filter(Mission.status == "ACTIVE").count(), "total_missions": db.query(Mission).count(),
                "personnel": db.query(Personnel).count(), "overdue_teams": len(sar.overdue_teams(db, now)),
                "assets": db.query(Asset).filter(Asset.status != "Retired").count(), "cargo_in_transit": db.query(CargoItem).filter(CargoItem.status == "in_transit").count(),
                "critical_alerts": sum(1 for a in al if a["level"] == "r"), "open_conflicts": db.query(SyncConflict).filter(SyncConflict.status == "open").count()},
        "alerts": al, "survival": inv_svc.survival(items), "cold": cold,
        "fuel": None if not bulk else {"bulk_l": bulk.qty, "burn_l_per_day": bulk.daily_use, "days": round(inv_svc.days_left(bulk)), "traverse_reserve_l": trav.qty if trav else None},
        "weather": None if not wx else {"temp_c": wx.temp_c, "wind_kt": wx.wind_kt, "gust_kt": wx.gust_kt, "wind_dir": wx.wind_dir, "vis_km": wx.vis_km, "pressure_hpa": wx.pressure_hpa, "at": iso(wx.at)},
        "server_time": iso(now), "server_clock": sync.server_clock(db),
    }


# ------------------------------------------------------------ geo
@router.get("/geo/coastline")
def coastline():
    return geo.load_geojson("coastline")


@router.get("/geo/iceshelves")
def iceshelves():
    return geo.load_geojson("iceshelves")


@router.get("/geo/seaice")
def seaice():
    return geo.seaice_geojson()


@router.get("/geo/features")
def features(db: Session = Depends(get_db)):
    """Points and lines from the database (stations, teams, vessel, routes, assets in the sector, incident)."""
    def pt(lat, lon, **props):
        return {"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
    inside = lambda lat, lon: -80 <= lat <= -56 and -10 <= lon <= 120
    feats = [pt(s.lat, s.lon, layer="station", name=s.name, code=s.code, kind=s.kind, approx=s.approx) for s in db.query(Station).all() if inside(s.lat, s.lon)]
    now = utcnow()
    by = {}
    for p in db.query(Personnel).all():
        by.setdefault(p.team, []).append(p)
    for team, members in by.items():
        st = sar.team_state(members, now)
        if inside(st["lat"], st["lon"]) and team not in ("Base-Bharati", "Base-Maitri"):
            feats.append(pt(st["lat"], st["lon"], layer="team", name=f"Team {team}", team=team, overdue_min=st["overdue_min"]))
    for a in db.query(Asset).filter(Asset.status != "Retired").all():
        if inside(a.lat, a.lon) and a.type in ("Snowcat", "UAV", "Cold storage"):
            feats.append(pt(a.lat, a.lon, layer="asset", name=a.id, type=a.type, status=a.status))
    for r in db.query(Route).all():
        feats.append({"type": "Feature", "properties": {"layer": "route", "name": r.name, "id": r.id, "kind": r.kind},
                      "geometry": {"type": "LineString", "coordinates": [[w[1], w[0]] for w in r.waypoints]}})
    inc = db.query(Incident).filter(Incident.state != "CLOSED").order_by(Incident.opened_at.desc()).first()
    if inc:
        feats.append(pt(inc.last_lat, inc.last_lon, layer="incident", name=inc.id, team=inc.team))
        for c in inc.grid["cells"]:
            feats.append({"type": "Feature", "properties": {"layer": "sar_cell", "p": c["p"]},
                          "geometry": {"type": "Polygon", "coordinates": [[[c["lon0"], c["lat0"]], [c["lon1"], c["lat0"]], [c["lon1"], c["lat1"]], [c["lon0"], c["lat1"]], [c["lon0"], c["lat0"]]]]}})
    return {"type": "FeatureCollection", "features": feats}


# ------------------------------------------------------------ sync API
class EventIn(BaseModel):
    event_id: str = Field(min_length=8, max_length=60)
    type: str
    entity_id: str = ""
    payload: dict = {}
    clock: int = Field(0, ge=0)
    base_clock: int = Field(0, ge=0)
    created_at: str


class PushIn(BaseModel):
    device_id: str = Field(min_length=2, max_length=60)
    events: List[EventIn] = Field(max_length=200)


def _parse_dt(s: str):
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"Bad timestamp: {s}")
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


@router.post("/sync/push")
def sync_push(body: PushIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    evs = [Ev(event_id=e.event_id, type=e.type, entity_id=e.entity_id, payload=e.payload, clock=e.clock, created_at=_parse_dt(e.created_at), base_clock=e.base_clock) for e in body.events]
    return sync.push(db, user, body.device_id, evs)


@router.get("/sync/pull")
def sync_pull(since: int = Query(0, ge=0), device_id: str = "", db: Session = Depends(get_db)):
    return sync.pull(db, since, device_id)


@router.get("/sync/log")
def sync_log(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    rows = db.query(SyncEvent).order_by(SyncEvent.seq.desc()).limit(limit).all()
    stats = {s: db.query(SyncEvent).filter(SyncEvent.status == s).count() for s in ("accepted", "rejected", "conflict")}
    return {"stats": stats, "server_clock": sync.server_clock(db),
            "events": [{"seq": r.seq, "event_id": r.event_id, "device_id": r.device_id, "type": r.type, "summary": sync.summarize(r), "status": r.status, "reason": r.reason, "at": iso(r.received_at)} for r in rows]}


@router.get("/sync/conflicts")
def conflicts(status: str = "open", db: Session = Depends(get_db)):
    q = db.query(SyncConflict)
    if status != "all":
        q = q.filter(SyncConflict.status == status)
    return [sync.conflict_dict(c) for c in q.order_by(SyncConflict.id.desc()).limit(100).all()]


class ResolveIn(BaseModel):
    choice: str


@router.post("/sync/conflicts/{cid}/resolve")
def resolve(cid: int, body: ResolveIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    try:
        return sync.resolve_conflict(db, user, cid, body.choice)
    except Exception as e:
        from ..services.rules import RuleViolation
        if isinstance(e, RuleViolation):
            raise HTTPException(409, str(e))
        raise


# ------------------------------------------------------------ assistant
class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)


@router.get("/assistant/suggestions")
def suggestions():
    return assistant.SUGGESTIONS


@router.post("/assistant/ask")
def ask(body: AskIn, db: Session = Depends(get_db)):
    return assistant.ask(db, body.question)


# ------------------------------------------------------------ reports
def _csv(name: str, header: list, rows) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/audit")
def audit_list(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"id": r.id, "at": iso(r.at), "user": r.username, "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail} for r in rows]


@router.get("/reports/audit.csv")
def audit_csv(db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    rows = db.query(AuditLog).order_by(AuditLog.id).all()
    return _csv("audit_log.csv", ["at", "user", "action", "entity", "entity_id", "detail"], [(iso(r.at), r.username, r.action, r.entity, r.entity_id, r.detail) for r in rows])


@router.get("/reports/incidents.csv")
def incidents_csv(db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    rows = db.query(Incident).order_by(Incident.opened_at).all()
    return _csv("incidents.csv", ["id", "team", "state", "opened_at", "closed_at", "overdue_min", "last_lat", "last_lon"], [(r.id, r.team, r.state, iso(r.opened_at), iso(r.closed_at), r.overdue_min, r.last_lat, r.last_lon) for r in rows])


@router.get("/reports/cargo-history.csv")
def cargo_csv(db: Session = Depends(get_db)):
    rows = db.query(CargoHandoff).order_by(CargoHandoff.at).all()
    return _csv("cargo_history.csv", ["cargo_id", "from", "to", "at", "by", "device"], [(r.cargo_id, r.from_node, r.to_node, iso(r.at), r.username, r.device_id) for r in rows])


@router.get("/reports/sync-events.csv")
def sync_csv(db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    rows = db.query(SyncEvent).order_by(SyncEvent.seq).all()
    return _csv("sync_events.csv", ["seq", "event_id", "device", "type", "entity", "status", "reason", "received_at"], [(r.seq, r.event_id, r.device_id, r.type, r.entity_id, r.status, r.reason, iso(r.received_at)) for r in rows])
