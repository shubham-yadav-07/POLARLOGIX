"""Missions, assets, personnel, inventory. Writes go through the sync engine."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models import Asset, InventoryItem, Mission, Personnel, User, utcnow
from ..security import OPS, current_user, require_roles
from ..serializers import asset_dict, mission_dict, person_dict
from ..services import inventory as inv_svc
from ..services import sar, sync

router = APIRouter(prefix="/api", tags=["operations"], dependencies=[Depends(current_user)])


def _ok(res: dict) -> dict:
    if res["status"] in ("rejected", "conflict"):
        raise HTTPException(409, res["reason"] or res["status"])
    return res


# ------------------------------------------------------------ missions
class MissionIn(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    org: str = ""
    base: str = Field(min_length=2)
    destination: str = ""
    objective: str = ""
    start_date: str = ""
    end_date: str = ""


class StatusIn(BaseModel):
    status: str


@router.get("/missions")
def missions(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Mission)
    if status:
        q = q.filter(Mission.status == status.upper())
    return [mission_dict(m, db) for m in q.order_by(Mission.id).all()]


@router.get("/missions/{mid}")
def mission(mid: str, db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m:
        raise HTTPException(404, "Unknown mission")
    return mission_dict(m, db)


@router.post("/missions", status_code=201)
def create_mission(body: MissionIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    n = db.query(Mission).count() + 1
    m = Mission(id=f"EXP-{utcnow().year % 100}-{n:02d}", name=body.name, org=body.org, base=body.base, destination=body.destination, status="PLANNED",
                risk_rating="MEDIUM", progress=0, start_date=body.start_date, end_date=body.end_date, objective=body.objective)
    db.add(m)
    audit(db, user.username, "mission_create", "mission", m.id, {"name": m.name})
    db.commit()
    return mission_dict(m, db)


@router.patch("/missions/{mid}/status")
def mission_status(mid: str, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*OPS))):
    return _ok(sync.submit(db, user, "EDIT", mid, {"entity": "mission", "field": "status", "value": body.status.upper()}))


# ------------------------------------------------------------ assets
class AssetIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    type: str
    station: str = "Bharati"
    id: Optional[str] = None


class AssetPatch(BaseModel):
    status: Optional[str] = None
    level_pct: Optional[int] = None


@router.get("/assets")
def assets(type: Optional[str] = None, station: Optional[str] = None, q: Optional[str] = None, limit: int = Query(200, le=500), db: Session = Depends(get_db)):
    query = db.query(Asset)
    if type:
        query = query.filter(Asset.type == type)
    if station:
        query = query.filter(Asset.station == station)
    if q:
        query = query.filter(Asset.id.ilike(f"%{q}%") | Asset.name.ilike(f"%{q}%"))
    total = query.count()
    rows = query.order_by(Asset.id).limit(limit).all()
    types = [t for (t,) in db.query(Asset.type).distinct().order_by(Asset.type).all()]
    return {"total": total, "types": types, "items": [asset_dict(a) for a in rows]}


@router.post("/assets", status_code=201)
def create_asset(body: AssetIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["ASSET_ADD"]))):
    from uuid import uuid4
    aid = body.id or f"AST-{body.type[:4].upper()}-{uuid4().hex[:5].upper()}"
    _ok(sync.submit(db, user, "ASSET_ADD", aid, {"id": aid, "name": body.name, "type": body.type, "station": body.station}))
    return asset_dict(db.get(Asset, aid))


@router.patch("/assets/{aid}")
def patch_asset(aid: str, body: AssetPatch, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["EDIT"]))):
    if db.get(Asset, aid) is None:
        raise HTTPException(404, "Unknown asset")
    for f, v in (("status", body.status), ("level_pct", body.level_pct)):
        if v is not None:
            _ok(sync.submit(db, user, "EDIT", aid, {"entity": "asset", "field": f, "value": v}))
    return asset_dict(db.get(Asset, aid))


# ------------------------------------------------------------ personnel
class CheckinIn(BaseModel):
    team: Optional[str] = None
    person_id: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)


@router.get("/personnel")
def personnel(team: Optional[str] = None, db: Session = Depends(get_db)):
    now = utcnow()
    q = db.query(Personnel)
    if team:
        q = q.filter(Personnel.team == team)
    rows = q.order_by(Personnel.team, Personnel.id).all()
    return {"total": len(rows), "items": [person_dict(p, now) for p in rows]}


@router.get("/teams")
def teams(db: Session = Depends(get_db)):
    now = utcnow()
    by = {}
    for p in db.query(Personnel).all():
        by.setdefault(p.team, []).append(p)
    out = []
    for name, members in by.items():
        st = sar.team_state(members, now)
        out.append({"team": name, "members": st["members"], "overdue_min": st["overdue_min"], "interval_min": st["interval"], "lat": st["lat"], "lon": st["lon"],
                    "next_due_at": st["next_due_at"].isoformat() + "Z", "station": members[0].station})
    return sorted(out, key=lambda t: t["team"])


@router.post("/checkins", status_code=201)
def checkin(body: CheckinIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["CHECKIN"]))):
    if not (body.team or body.person_id):
        raise HTTPException(422, "team or person_id is required")
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return _ok(sync.submit(db, user, "CHECKIN", body.team or body.person_id, payload))


# ------------------------------------------------------------ inventory
class AdjustIn(BaseModel):
    delta: float
    reason: str = ""


class SetIn(BaseModel):
    field: str = Field(pattern="^(qty|min_qty|daily_use)$")
    value: float = Field(ge=0)


@router.get("/inventory")
def inventory(db: Session = Depends(get_db)):
    items = db.query(InventoryItem).order_by(InventoryItem.category, InventoryItem.id).all()
    by = {i.id: i for i in items}
    bulk, trav = by.get("INV-DIESEL-S"), by.get("INV-DIESEL-T")
    return {"items": [inv_svc.serialize(i) for i in items], "survival": inv_svc.survival(items),
            "fuel": None if not bulk else {"bulk_l": bulk.qty, "burn_l_per_day": bulk.daily_use, "days": round(inv_svc.days_left(bulk)), "traverse_reserve_l": trav.qty if trav else None}}


@router.post("/inventory/{iid}/adjust")
def adjust(iid: str, body: AdjustIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["STOCK"]))):
    if db.get(InventoryItem, iid) is None:
        raise HTTPException(404, "Unknown item")
    _ok(sync.submit(db, user, "STOCK", iid, {"item_id": iid, "delta": body.delta, "reason": body.reason}))
    return inv_svc.serialize(db.get(InventoryItem, iid))


@router.patch("/inventory/{iid}")
def set_value(iid: str, body: SetIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*sync.EVENT_ROLES["EDIT"]))):
    if db.get(InventoryItem, iid) is None:
        raise HTTPException(404, "Unknown item")
    _ok(sync.submit(db, user, "EDIT", iid, {"entity": "inventory", "field": body.field, "value": body.value}))
    return inv_svc.serialize(db.get(InventoryItem, iid))
