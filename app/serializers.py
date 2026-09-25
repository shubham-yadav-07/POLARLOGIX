from datetime import datetime

from .models import Asset, CargoItem, Mission, Personnel, iso, utcnow
from .services import rules


def person_dict(p: Personnel, now: datetime = None) -> dict:
    now = now or utcnow()
    mins_to_due = (p.next_due_at - now).total_seconds() / 60
    status = "missed" if mins_to_due < 0 else "due_soon" if mins_to_due < 20 else "ok"
    return {"id": p.id, "name": p.name, "role": p.role, "team": p.team, "mission_id": p.mission_id, "station": p.station, "lat": p.lat, "lon": p.lon,
            "interval_min": p.checkin_interval_min, "last_checkin_at": iso(p.last_checkin_at), "next_due_at": iso(p.next_due_at),
            "minutes_to_due": round(mins_to_due), "status": status}


def asset_dict(a: Asset) -> dict:
    return {"id": a.id, "name": a.name, "type": a.type, "station": a.station, "status": a.status, "level_pct": a.level_pct, "lat": a.lat, "lon": a.lon,
            "mission_id": a.mission_id, "last_seen_at": iso(a.last_seen_at)}


def cargo_dict(c: CargoItem) -> dict:
    chk = rules.check_item(c)
    return {"id": c.id, "consignment": c.consignment, "name": c.name, "weight_kg": c.weight_kg, "category": c.category, "hazard": c.hazard, "route": c.route,
            "route_nodes": rules.route_nodes(c.route), "current_node": c.current_node, "next_node": rules.next_node(c.route, c.current_node),
            "status": c.status, "check": chk}


def mission_dict(m: Mission, db) -> dict:
    people = db.query(Personnel).filter(Personnel.mission_id == m.id).all()
    assets = db.query(Asset).filter(Asset.mission_id == m.id).all()
    today = utcnow().strftime("%Y-%m-%d")
    if not m.permit_valid_until:
        permit = "PENDING"
    else:
        permit = "VALID" if m.permit_valid_until >= today else "EXPIRED"
    return {"id": m.id, "name": m.name, "org": m.org, "base": m.base, "destination": m.destination, "status": m.status, "risk_rating": m.risk_rating,
            "progress": m.progress, "start_date": m.start_date, "end_date": m.end_date, "objective": m.objective, "route_id": m.route_id,
            "permit": permit, "permit_valid_until": m.permit_valid_until,
            "team": [{"id": p.id, "name": p.name, "role": p.role, "team": p.team} for p in people],
            "team_size": len(people), "asset_count": len(assets), "assets": [a.id for a in assets[:8]]}
