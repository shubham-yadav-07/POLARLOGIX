"""Days-left forecasting and the 5-day survival check."""
SURVIVAL_MIN_DAYS = 5.0
SURVIVAL_CATEGORIES = {"food": "Food (ration packs)", "fuel": "Diesel (heating / melt)", "water": "Melt-water production"}


def days_left(item) -> float:
    return 999.0 if item.daily_use <= 0 else item.qty / item.daily_use


def status(item) -> str:
    if item.qty < item.min_qty:
        return "below_min"
    if item.qty < item.min_qty * 1.3:
        return "watch"
    return "ok"


def serialize(item) -> dict:
    d = days_left(item)
    return {"id": item.id, "name": item.name, "category": item.category, "qty": item.qty, "unit": item.unit,
            "daily_use": item.daily_use, "min_qty": item.min_qty, "station": item.station,
            "days_left": round(min(d, 999.0), 1), "status": status(item)}


def survival(items) -> dict:
    rows = []
    for cat, label in SURVIVAL_CATEGORIES.items():
        pool = [i for i in items if i.category == cat]
        if not pool:
            continue
        worst = min(pool, key=days_left)
        rows.append({"category": cat, "label": label, "item": worst.name, "days": round(days_left(worst), 1),
                     "pass": days_left(worst) >= SURVIVAL_MIN_DAYS})
    return {"required_days": SURVIVAL_MIN_DAYS, "passed": all(r["pass"] for r in rows) if rows else False, "rows": rows}
