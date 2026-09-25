"""Offline-first sync engine.

Every write in the system is an EVENT (uuid, device, type, payload, logical clock).
Field devices write events locally and push them in batches; the HQ web app uses
the same code path with device_id = "HQ".

Rules
  * duplicate event_id            -> ignored (idempotent)
  * business rule broken          -> rejected with a reason (nothing is applied)
  * EDIT of a simple field        -> last write wins on (clock, device_id)
  * EDIT of a SAFETY field that   -> BOTH versions kept: the server value stays,
    was changed elsewhere since      the device value is stored in sync_conflicts
    the device last synced           and an operator resolves it (audited)
  * STOCK / CHECKIN / HANDOFF     -> commutative or append-only, no conflicts
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from ..audit import audit
from ..models import (Asset, CargoHandoff, CargoItem, Checkin, FieldVersion, Incident, IncidentAction, InventoryItem, Mission,
                      Personnel, Sample, SensorReading, Station, StockMovement, SyncConflict, SyncEvent, SyncState, User, iso, utcnow)
from . import rules


class ConflictOutcome(Exception):
    pass


@dataclass
class Ev:
    event_id: str
    type: str
    entity_id: str
    payload: dict
    clock: int = 0
    created_at: datetime = field(default_factory=utcnow)
    base_clock: int = 0


EVENT_ROLES = {
    "CHECKIN": ("manager", "leader", "field"),
    "HANDOFF": ("manager", "leader", "logistics", "field"),
    "STOCK": ("manager", "leader", "logistics", "field"),
    "READING": ("manager", "leader", "logistics", "field"),
    "EDIT": ("manager", "leader", "logistics"),
    "ASSET_ADD": ("manager", "leader", "logistics"),
}
ENTITIES = {
    "inventory": (InventoryItem, {"qty": float, "min_qty": float, "daily_use": float}),
    "asset": (Asset, {"status": str, "level_pct": int, "name": str, "station": str}),
    "mission": (Mission, {"status": str, "progress": int}),
}
SAFETY_FIELDS = {("inventory", "qty"), ("inventory", "min_qty")}     # conflicts on these are never auto-resolved
ASSET_STATUSES = {"Available", "In use", "Running", "Maintenance", "Retired"}
MISSION_STATUSES = {"PLANNED", "ACTIVE", "PAUSED", "COMPLETED", "CANCELLED"}


# ------------------------------------------------------------------ clock
def _state(db: Session) -> SyncState:
    s = db.get(SyncState, 1, with_for_update=True)
    if s is None:
        s = SyncState(id=1, clock=0)
        db.add(s)
        db.flush()
    return s


def server_clock(db: Session) -> int:
    return _state(db).clock


def tick(db: Session, at_least: int = 0) -> int:
    s = _state(db)
    s.clock = max(s.clock, at_least) + 1
    return s.clock


def _fv(db: Session, entity: str, eid: str, fld: str) -> Optional[FieldVersion]:
    return db.get(FieldVersion, (entity, eid, fld))


def _fv_set(db: Session, entity: str, eid: str, fld: str, value, clock: int, device: str) -> None:
    row = _fv(db, entity, eid, fld)
    if row is None:
        db.add(FieldVersion(entity=entity, entity_id=eid, field=fld, value={"v": value}, clock=clock, device_id=device, updated_at=utcnow()))
    else:
        row.value, row.clock, row.device_id, row.updated_at = {"v": value}, clock, device, utcnow()


# ------------------------------------------------------------------ handlers
def _h_checkin(db, user, device, ev, now):
    p = ev.payload
    if p.get("person_id"):
        members = db.query(Personnel).filter(Personnel.id == p["person_id"]).all()
    elif p.get("team"):
        members = db.query(Personnel).filter(Personnel.team == p["team"]).all()
    else:
        members = []
    if not members:
        raise rules.RuleViolation("Unknown team or person")
    at = min(ev.created_at, now)
    lat, lon = p.get("lat"), p.get("lon")
    team = members[0].team
    newest = False
    for m in members:
        if at >= m.last_checkin_at:
            newest = True
            m.last_checkin_at = at
            m.next_due_at = at + timedelta(minutes=m.checkin_interval_min)
            m.hold = False
            if lat is not None and lon is not None:
                m.lat, m.lon = float(lat), float(lon)
    lead = members[0]
    db.add(Checkin(team=team, personnel_id=p.get("person_id"), lat=float(lat if lat is not None else lead.lat),
                   lon=float(lon if lon is not None else lead.lon), at=at, device_id=device, source="sync", event_id=ev.event_id))
    inc = db.query(Incident).filter(Incident.team == team, Incident.state != "CLOSED").first()
    if inc and newest:
        n = db.query(IncidentAction).filter(IncidentAction.incident_id == inc.id).count() + 1
        db.add(IncidentAction(incident_id=inc.id, step_no=n, title="Contact re-established", detail=f"Check-in received from team {team}. Operator can close the incident.", at=now))
    return {"note": f"{len(members)} member(s) updated"}


def _h_handoff(db, user, device, ev, now):
    item = db.get(CargoItem, ev.payload.get("cargo_id"))
    if item is None:
        raise rules.RuleViolation("Unknown cargo item")
    to_node = ev.payload.get("to_node", "")
    siblings = db.query(CargoItem).filter(CargoItem.consignment == item.consignment).all()
    rules.validate_handoff(item, to_node, siblings)
    db.add(CargoHandoff(cargo_id=item.id, from_node=item.current_node, to_node=to_node, at=min(ev.created_at, now), username=user.username, device_id=device, event_id=ev.event_id))
    item.current_node = to_node
    item.status = "delivered" if rules.next_node(item.route, to_node) is None else "in_transit"
    return {"note": f"{item.id} now at {to_node}"}


def _h_stock(db, user, device, ev, now):
    item = db.get(InventoryItem, ev.payload.get("item_id"))
    if item is None:
        raise rules.RuleViolation("Unknown inventory item")
    delta = float(ev.payload.get("delta", 0))
    new = item.qty + delta
    note = ""
    if new < 0:
        delta, new, note = -item.qty, 0.0, "clamped at zero"
    item.qty = new
    db.add(StockMovement(item_id=item.id, delta=delta, reason=str(ev.payload.get("reason", ""))[:120], at=min(ev.created_at, now), device_id=device, event_id=ev.event_id))
    return {"note": note or f"{item.name} now {new:g} {item.unit}"}


def _h_reading(db, user, device, ev, now):
    p = ev.payload
    if db.get(Sample, p.get("sample_id")) is None:
        raise rules.RuleViolation("Unknown sample")
    at = p.get("at")
    at = datetime.fromisoformat(at.replace("Z", "")) if isinstance(at, str) else min(ev.created_at, now)
    db.add(SensorReading(sample_id=p["sample_id"], at=at, temp_c=float(p["temp_c"]), ambient_c=p.get("ambient_c"), source="field"))
    return {"note": "reading stored"}


def _h_asset_add(db, user, device, ev, now):
    p = ev.payload
    aid = p.get("id") or ev.entity_id
    if not aid or not p.get("name"):
        raise rules.RuleViolation("Asset needs an id and a name")
    if db.get(Asset, aid):
        raise rules.RuleViolation(f"Asset {aid} already exists")
    st = db.get(Station, p.get("station", "Bharati"))
    db.add(Asset(id=aid, name=p["name"][:80], type=p.get("type", "Other"), station=p.get("station", "Bharati"), status="Available", level_pct=100,
                 lat=p.get("lat", st.lat if st else 0.0), lon=p.get("lon", st.lon if st else 0.0), last_seen_at=now))
    return {"note": f"asset {aid} added"}


def _h_edit(db, user, device, ev, now):
    p = ev.payload
    ent, fld = p.get("entity"), p.get("field")
    if ent not in ENTITIES or fld not in ENTITIES[ent][1]:
        raise rules.RuleViolation(f"Cannot edit {ent}.{fld}")
    model, fields = ENTITIES[ent]
    obj = db.get(model, ev.entity_id)
    if obj is None:
        raise rules.RuleViolation(f"Unknown {ent} {ev.entity_id}")
    try:
        value = fields[fld](p.get("value"))
    except (TypeError, ValueError):
        raise rules.RuleViolation("Bad value")
    if ent == "asset" and fld == "status" and value not in ASSET_STATUSES:
        raise rules.RuleViolation("Unknown asset status")
    if ent == "mission" and fld == "status" and value not in MISSION_STATUSES:
        raise rules.RuleViolation("Unknown mission status")
    if fields[fld] in (int, float) and value < 0:
        raise rules.RuleViolation("Value cannot be negative")
    cur = _fv(db, ent, ev.entity_id, fld)
    current_value = getattr(obj, fld)
    if cur is not None and cur.device_id != device and cur.clock > ev.base_clock and cur.value["v"] != value and (ent, fld) in SAFETY_FIELDS:
        db.add(SyncConflict(entity=ent, entity_id=ev.entity_id, field=fld, server_value={"v": current_value}, device_value={"v": value},
                            server_clock=cur.clock, device_clock=ev.clock, server_device=cur.device_id, device_id=device, event_id=ev.event_id))
        raise ConflictOutcome(f"{ent}.{fld} was changed by {cur.device_id} after this device last synced")
    if cur is not None and (ev.clock, device) <= (cur.clock, cur.device_id):
        return {"note": "older than the current value, ignored (last write wins)"}
    setattr(obj, fld, value)
    _fv_set(db, ent, ev.entity_id, fld, value, ev.clock, device)
    return {"note": f"{ent} {ev.entity_id} {fld} = {value}"}


HANDLERS = {"CHECKIN": _h_checkin, "HANDOFF": _h_handoff, "STOCK": _h_stock, "READING": _h_reading, "ASSET_ADD": _h_asset_add, "EDIT": _h_edit}


# ------------------------------------------------------------------ processing
def _process(db: Session, user: User, device: str, ev: Ev) -> dict:
    if db.query(SyncEvent.seq).filter(SyncEvent.event_id == ev.event_id).first():
        return {"event_id": ev.event_id, "status": "duplicate", "reason": "already processed"}
    now = utcnow()
    row = SyncEvent(event_id=ev.event_id, device_id=device, user_id=user.id, type=ev.type, entity_id=ev.entity_id, payload=ev.payload,
                    clock=ev.clock, created_at=min(ev.created_at, now + timedelta(minutes=5)), received_at=now, status="accepted")
    handler = HANDLERS.get(ev.type)
    if handler is None:
        row.status, row.reason = "rejected", f"Unknown event type {ev.type}"
    elif user.role not in EVENT_ROLES[ev.type]:
        row.status, row.reason = "rejected", f"Role '{user.role}' may not send {ev.type}"
    else:
        try:
            out = handler(db, user, device, ev, now)
            row.reason = out.get("note", "")[:240]
        except rules.RuleViolation as e:
            row.status, row.reason = "rejected", str(e)[:240]
        except ConflictOutcome as e:
            row.status, row.reason = "conflict", str(e)[:240]
    db.add(row)
    db.flush()
    tick(db, ev.clock)
    if row.status != "rejected":
        audit(db, user.username, "sync_" + ev.type.lower(), "event", ev.event_id, {"device": device, "status": row.status, "entity": ev.entity_id})
    return {"event_id": ev.event_id, "status": row.status, "reason": row.reason, "seq": row.seq}


def push(db: Session, user: User, device: str, events: list) -> dict:
    results = [_process(db, user, device, ev) for ev in sorted(events, key=lambda e: (e.clock, e.created_at, e.event_id))]
    db.commit()
    seq = db.query(SyncEvent.seq).order_by(SyncEvent.seq.desc()).first()
    return {"results": results, "server_clock": server_clock(db), "cursor": seq[0] if seq else 0}


def submit(db: Session, user: User, type_: str, entity_id: str, payload: dict) -> dict:
    """Same path as a device push, used by the HQ web app (device 'HQ')."""
    ev = Ev(event_id=f"hq-{uuid4()}", type=type_, entity_id=entity_id, payload=payload, clock=server_clock(db) + 1, created_at=utcnow(), base_clock=server_clock(db))
    res = _process(db, user, "HQ", ev)
    db.commit()
    return res


def summarize(ev: SyncEvent) -> str:
    p = ev.payload or {}
    if ev.type == "CHECKIN":
        return f"Check-in: {p.get('team') or p.get('person_id')}"
    if ev.type == "HANDOFF":
        return f"Cargo {p.get('cargo_id')} to {p.get('to_node')}"
    if ev.type == "STOCK":
        return f"Stock {p.get('item_id')} {float(p.get('delta', 0)):+g}"
    if ev.type == "EDIT":
        return f"{ev.entity_id}: {p.get('field')} = {p.get('value')}"
    if ev.type == "ASSET_ADD":
        return f"Asset added: {p.get('id') or ev.entity_id}"
    return f"{ev.type} {ev.entity_id}"


def pull(db: Session, since: int, device: str, limit: int = 200) -> dict:
    rows = db.query(SyncEvent).filter(SyncEvent.seq > since, SyncEvent.status != "rejected").order_by(SyncEvent.seq).limit(limit).all()
    cursor = rows[-1].seq if rows else since
    return {"changes": [{"seq": r.seq, "type": r.type, "entity_id": r.entity_id, "device_id": r.device_id, "status": r.status,
                         "summary": summarize(r), "at": iso(r.received_at), "own": r.device_id == device} for r in rows],
            "cursor": cursor, "server_clock": server_clock(db),
            "open_conflicts": db.query(SyncConflict).filter(SyncConflict.status == "open").count()}


def conflict_dict(c: SyncConflict) -> dict:
    return {"id": c.id, "entity": c.entity, "entity_id": c.entity_id, "field": c.field, "server_value": c.server_value["v"],
            "device_value": c.device_value["v"], "server_device": c.server_device, "device_id": c.device_id, "status": c.status,
            "resolution": c.resolution, "resolved_by": c.resolved_by, "created_at": iso(c.created_at)}


def resolve_conflict(db: Session, user: User, cid: int, choice: str) -> dict:
    c = db.get(SyncConflict, cid)
    if c is None:
        raise rules.RuleViolation("Unknown conflict")
    if c.status != "open":
        raise rules.RuleViolation("Already resolved")
    if choice not in ("server", "device"):
        raise rules.RuleViolation("choice must be 'server' or 'device'")
    if choice == "device":
        model, fields = ENTITIES[c.entity]
        obj = db.get(model, c.entity_id)
        setattr(obj, c.field, c.device_value["v"])
        _fv_set(db, c.entity, c.entity_id, c.field, c.device_value["v"], tick(db, c.device_clock), "HQ")
    c.status, c.resolution, c.resolved_by, c.resolved_at = "resolved", choice, user.username, utcnow()
    audit(db, user.username, "conflict_resolved", c.entity, c.entity_id, {"field": c.field, "kept": choice, "server": c.server_value["v"], "device": c.device_value["v"]})
    db.commit()
    return conflict_dict(c)
