"""Cargo and air-freight rules (data/cargo_rules.json).

Rules that come from NCPOR ISEA advertisements carry verified=True in the JSON;
anything assumed for the prototype carries verified=False. Check the current
advisory before real use.
"""
import json
from functools import lru_cache
from typing import Optional

from ..config import settings


class RuleViolation(Exception):
    pass


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads((settings.data_dir / "cargo_rules.json").read_text())


def route_nodes(route: str) -> list:
    return rules()["routes"][route]


def next_node(route: str, current: str) -> Optional[str]:
    nodes = route_nodes(route)
    if current not in nodes:
        return None
    i = nodes.index(current)
    return nodes[i + 1] if i + 1 < len(nodes) else None


def check_item(item) -> dict:
    """Pre-departure check for one cargo item (object with .category .route .hazard .weight_kg)."""
    r = rules()
    if item.hazard and item.route == "air":
        return {"code": "NO_AIR", "label": "NO AIR", "level": "r", "message": r["hazard_rule"]["text"]}
    if item.hazard and item.category in r["arrange_at_cape_town"]:
        return {"code": "ARRANGE_CT", "label": "ARRANGE AT CAPE TOWN", "level": "a", "message": "Fuel is bought or arranged at Cape Town and shipped, not flown from India."}
    if item.hazard:
        return {"code": "SHIP_ONLY", "label": "SHIP ONLY", "level": "a", "message": r["hazard_rule"]["text"]}
    if item.category in r["declaration_required"]:
        return {"code": "DECLARATION", "label": "DECLARATION", "level": "a", "message": r["declaration_required"][item.category]}
    return {"code": "OK", "label": "OK", "level": "g", "message": "No rule triggered"}


def check_consignment(items) -> dict:
    lim = rules()["air_limit_kg"]
    air = sum(i.weight_kg for i in items if i.route == "air")
    if air > lim["max"]:
        state = "over"
    elif air > lim["min"]:
        state = "warn"
    else:
        state = "ok"
    return {"air_kg": air, "limit_min": lim["min"], "limit_max": lim["max"], "state": state,
            "items": [{"id": i.id, **check_item(i)} for i in items]}


def validate_handoff(item, to_node: str, siblings) -> None:
    """Raise RuleViolation if this handoff breaks a rule."""
    r = rules()
    expected = next_node(item.route, item.current_node)
    if expected is None:
        raise RuleViolation(f"{item.id} is already at the end of its route ({item.current_node})")
    if to_node != expected:
        raise RuleViolation(f"Out of order: {item.id} goes {item.current_node} -> {expected}, not {to_node}")
    if to_node in r["air_nodes"]:
        if item.hazard:
            raise RuleViolation(f"{item.name} is hazardous and cannot go by air")
        air = sum(s.weight_kg for s in siblings if s.route == "air")
        if air > r["air_limit_kg"]["max"]:
            raise RuleViolation(f"Air cargo for {item.consignment} is {air:.0f} kg, over the {r['air_limit_kg']['max']} kg limit")
