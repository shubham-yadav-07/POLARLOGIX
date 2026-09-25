"""Live alerts, computed from the current data (nothing is hard-coded)."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Incident, InventoryItem, Sample, SensorReading, SyncConflict, iso, utcnow
from . import coldchain, inventory, sar


def cold_analysis(db: Session, sample: Sample) -> dict:
    rows = db.query(SensorReading).filter(SensorReading.sample_id == sample.id).order_by(SensorReading.at).all()
    res = coldchain.analyze([(r.at, r.temp_c) for r in rows], sample.limit_c)
    res.update({"sample_id": sample.id, "container_id": sample.container_id, "description": sample.description,
                "simulated": any(r.source == "simulated" for r in rows), "last_reading_at": iso(rows[-1].at) if rows else None})
    return res


def compute(db: Session, now: Optional[datetime] = None) -> list:
    now = now or utcnow()
    out = []
    for inc in db.query(Incident).filter(Incident.state != "CLOSED").all():
        out.append({"id": f"inc-{inc.id}", "level": "r", "title": f"{inc.id}: team {inc.team} not responding",
                    "detail": f"Missed check-in by {inc.overdue_min} min. Last position {inc.last_lat:.3f}, {inc.last_lon:.3f}.", "at": iso(inc.opened_at), "go": "sar", "cta": "Open SAR hub"})
    open_teams = {i.team for i in db.query(Incident).filter(Incident.state != "CLOSED").all()}
    for st in sar.overdue_teams(db, now):
        if st["team"] in open_teams:
            continue
        lvl = "r" if st["overdue_min"] > sar.GRACE_MIN else "a"
        out.append({"id": f"miss-{st['team']}", "level": lvl, "title": f"Missed check-in: team {st['team']}",
                    "detail": f"{st['overdue_min']} min past the {st['interval']} min interval. Verify by beacon or radio.", "at": iso(st["next_due_at"]), "go": "sar", "cta": "Open SAR hub"})
    for s in db.query(Sample).all():
        a = cold_analysis(db, s)
        if a["status"] in ("warning", "critical", "breached"):
            eta = "limit already crossed" if a["status"] == "breached" else f"breach of {s.limit_c:g} C in about {a['eta_h']} h"
            out.append({"id": f"cold-{s.id}", "level": "r" if a["status"] != "warning" else "a", "title": f"Cold-chain: {s.id}",
                        "detail": f"{s.container_id} at {a['current']} C, warming {a['rate_c_per_h']:+.2f} C/h. Predicted {eta}.", "at": a["last_reading_at"], "go": "cold", "cta": "Open cold-chain"})
    items = db.query(InventoryItem).all()
    for i in items:
        if inventory.status(i) == "below_min":
            out.append({"id": f"stock-{i.id}", "level": "a", "title": f"Below minimum: {i.name}",
                        "detail": f"{i.qty:g} {i.unit} left, minimum {i.min_qty:g}. About {inventory.days_left(i):.1f} days at current use.", "at": iso(now), "go": "inv", "cta": "Open inventory"})
    surv = inventory.survival(items)
    if not surv["passed"]:
        bad = ", ".join(r["item"] for r in surv["rows"] if not r["pass"])
        out.append({"id": "survival", "level": "r", "title": "5-day survival check failed", "detail": f"Below {surv['required_days']:g} days: {bad}.", "at": iso(now), "go": "inv", "cta": "Open inventory"})
    n = db.query(SyncConflict).filter(SyncConflict.status == "open").count()
    if n:
        out.append({"id": "conflicts", "level": "a", "title": f"{n} sync conflict(s) need review", "detail": "Two versions of a safety field were kept. Choose one.", "at": iso(now), "go": "sync", "cta": "Review conflicts"})
    order = {"r": 0, "a": 1, "b": 2}
    return sorted(out, key=lambda a: (order[a["level"]], a["at"] or ""), reverse=False)
