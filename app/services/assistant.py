"""Records-only assistant.

It matches the question to a small set of tools (SQL queries over the operational
tables), builds the answer from the returned facts and lists the tables it used.
It never invents facts: if no tool matches it says so. An LLM could be added to
rephrase the answer, but the facts always come from the tools.
"""
from sqlalchemy.orm import Session

from ..models import CargoItem, Incident, InventoryItem, Sample
from . import alerts, inventory, risk, rules, sar
from ..models import utcnow

SUGGESTIONS = ["Why is the cold-chain alert open?", "Which stock runs out first?", "Can the battery go by air?",
               "What is the status of Team Bravo?", "What is the weather at Bharati?", "Is the 5-day survival check passing?"]


def _has(q: str, *words) -> bool:
    return any(w in q for w in words)


def ask(db: Session, question: str) -> dict:
    q = question.lower()
    if _has(q, "cold", "sample", "thermal", "freez", "ice core", "ice-core", "temperature"):
        rows = [alerts.cold_analysis(db, s) for s in db.query(Sample).all()]
        bad = [r for r in rows if r["status"] != "ok"]
        if not bad:
            return {"answer": "All samples are inside their limits and none is warming toward it.", "sources": ["samples", "sensor_readings"]}
        r = bad[0]
        eta = "already above its limit" if r["status"] == "breached" else f"predicted to reach {r['limit_c']:g} C in about {r['eta_h']} h"
        return {"answer": f"{r['sample_id']} in {r['container_id']} is at {r['current']} C and warming {r['rate_c_per_h']:+.2f} C per hour, so it is {eta}. "
                          f"{r['outliers']} sensor spike(s) were flagged and excluded from the trend. Suggested action: move it to a powered freezer before the next leg.",
                "sources": ["samples", "sensor_readings (last 24 h)", "coldchain.analyze"]}
    if _has(q, "stock", "run out", "inventory", "diesel", "food", "supply", "supplies", "fuel"):
        items = db.query(InventoryItem).filter(InventoryItem.daily_use > 0).all()
        i = min(items, key=inventory.days_left)
        low = [x.name for x in items if inventory.status(x) == "below_min"]
        tail = f" Below minimum now: {', '.join(low)}." if low else " Nothing is below its minimum."
        return {"answer": f"{i.name} runs out first: {i.qty:g} {i.unit} at {i.daily_use:g} per day is about {inventory.days_left(i):.1f} days.{tail}", "sources": ["inventory_items"]}
    if _has(q, "battery", "air", "flight", "cargo", "hazard", "fuel drum", "jet", "gas", "chemical", "weigh"):
        r = rules.rules()
        named = next((c for c in db.query(CargoItem).all() if c.name.lower().split()[0] in q), None)
        extra = ""
        if named:
            chk = rules.check_item(named)
            extra = f" For {named.name} ({named.id}, route {named.route}): {chk['label']}. {chk['message']}"
        return {"answer": f"{r['hazard_rule']['text']} {r['air_limit_kg']['note']}{extra}", "sources": ["cargo_rules.json (NCPOR ISEA advertisement)", "cargo_items"]}
    if _has(q, "team", "bravo", "alpha", "check-in", "checkin", "overdue", "missed", "personnel"):
        teams = {}
        from ..models import Personnel
        for p in db.query(Personnel).all():
            teams.setdefault(p.team, []).append(p)
        name = next((t for t in teams if t.lower() in q), "Bravo")
        st = sar.team_state(teams[name], utcnow())
        inc = db.query(Incident).filter(Incident.team == name, Incident.state != "CLOSED").first()
        if inc:
            return {"answer": f"Team {name} is overdue by {st['overdue_min']} min. Incident {inc.id} is {inc.state.lower()}, last position {inc.last_lat:.3f}, {inc.last_lon:.3f}, and a {len(inc.grid['cells'])}-cell search grid exists.", "sources": ["personnel", "incidents", "incident_actions"]}
        state = f"overdue by {st['overdue_min']} min" if st["overdue_min"] else "on schedule"
        return {"answer": f"Team {name} ({st['members']} people) is {state}. Last check-in at {st['last_checkin_at']:%H:%M} UTC, next due {st['next_due_at']:%H:%M} UTC. No incident is open.", "sources": ["personnel", "checkins"]}
    if _has(q, "weather", "wind", "visibility", "temperature outside", "gust"):
        w = risk.latest_weather(db, "Bharati")
        return {"answer": f"Bharati: {w.temp_c:.1f} C, wind {w.wind_kt:.0f} kt (gusts {w.gust_kt:.0f}) from {w.wind_dir} deg, visibility {w.vis_km:.1f} km, {w.pressure_hpa:.1f} hPa at {w.at:%H:%M} UTC. (Demo dataset.)", "sources": ["weather_readings"]}
    if _has(q, "survival", "5-day", "5 day"):
        s = inventory.survival(db.query(InventoryItem).all())
        rows = "; ".join(f"{r['label']}: {r['days']} d" for r in s["rows"])
        return {"answer": f"The 5-day survival check is {'passing' if s['passed'] else 'FAILING'}. {rows}.", "sources": ["inventory_items"]}
    if _has(q, "incident", "sar", "emergency", "rescue"):
        inc = db.query(Incident).filter(Incident.state != "CLOSED").first()
        return {"answer": "No incident is open." if not inc else f"{inc.id} for team {inc.team} is {inc.state.lower()}.", "sources": ["incidents"]}
    return {"answer": "I can only answer from the operational records (cold-chain, stock, cargo rules, teams, weather, survival check, incidents). I could not match that question to any of them.",
            "sources": []}
