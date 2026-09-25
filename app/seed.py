"""Create tables and load the datasets from ./data into an empty database."""
import csv
import json
import random
from datetime import timedelta

from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine
from .models import (Asset, CargoHandoff, CargoItem, EnvLayer, InventoryItem, Mission, Personnel, Route, Sample, SensorReading, Station,
                     SyncState, User, WeatherReading, utcnow)
from .security import hash_password
from .services import rules


def _rows(name):
    with open(settings.data_dir / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(User).count():
            return
        if settings.seed_demo_data:
            seed_demo(db)
        else:
            import os
            u, p = os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD")
            if u and p:
                db.add(User(username=u, password_hash=hash_password(p), full_name=u, role="manager", station=""))
            db.add(SyncState(id=1, clock=0))
            db.commit()


def seed_demo(db: Session) -> None:
    now = utcnow()
    pw = hash_password(settings.demo_password)
    for r in _rows("users.csv"):
        db.add(User(username=r["username"], password_hash=pw, full_name=r["full_name"], role=r["role"], station=r["station"]))
    for r in _rows("stations.csv"):
        db.add(Station(code=r["code"], name=r["name"], kind=r["kind"], lat=float(r["lat"]), lon=float(r["lon"]), approx=bool(int(r["approx"])), note=r["note"]))
    for r in _rows("missions.csv"):
        db.add(Mission(id=r["id"], name=r["name"], org=r["org"], base=r["base"], destination=r["destination"], status=r["status"], risk_rating=r["risk_rating"],
                       progress=int(r["progress"]), start_date=r["start_date"], end_date=r["end_date"], objective=r["objective"],
                       permit_valid_until=r["permit_valid_until"] or None, route_id=r["route_id"] or None))
    db.flush()
    for r in _rows("personnel.csv"):
        last = now - timedelta(minutes=int(r["last_checkin_min_ago"]))
        iv = int(r["checkin_interval_min"])
        db.add(Personnel(id=r["id"], name=r["name"], role=r["role"], team=r["team"], mission_id=r["mission_id"] or None, station=r["station"], lat=float(r["lat"]),
                         lon=float(r["lon"]), checkin_interval_min=iv, last_checkin_at=last, next_due_at=last + timedelta(minutes=iv)))
    for i, r in enumerate(_rows("assets.csv")):
        db.add(Asset(id=r["id"], name=r["name"], type=r["type"], station=r["station"], status=r["status"], level_pct=int(r["level_pct"]), lat=float(r["lat"]),
                     lon=float(r["lon"]), mission_id=r["mission_id"] or None, last_seen_at=now - timedelta(minutes=2 + (i * 7) % 90)))
    for r in _rows("inventory.csv"):
        db.add(InventoryItem(id=r["id"], name=r["name"], category=r["category"], qty=float(r["qty"]), unit=r["unit"], daily_use=float(r["daily_use"]),
                             min_qty=float(r["min_qty"]), station=r["station"]))
    rnd = random.Random(7)
    for r in _rows("cargo.csv"):
        item = CargoItem(id=r["id"], consignment=r["consignment"], name=r["name"], weight_kg=float(r["weight_kg"]), category=r["category"], hazard=bool(int(r["hazard"])),
                         route=r["route"], current_node=r["current_node"], status=r["status"])
        db.add(item)
        nodes = rules.route_nodes(item.route)
        upto = nodes.index(item.current_node) if item.current_node in nodes else 0
        for k in range(upto):        # chain-of-custody history for the nodes already passed
            db.add(CargoHandoff(cargo_id=item.id, from_node=nodes[k], to_node=nodes[k + 1], at=now - timedelta(days=(upto - k) * 6 + rnd.randint(0, 3)),
                                username="logistics", device_id="seed"))
    for r in _rows("samples.csv"):
        db.add(Sample(id=r["id"], container_id=r["container_id"], description=r["description"], limit_c=float(r["limit_c"]), mission_id=r["mission_id"]))
    db.flush()
    for r in _rows("sensor_readings.csv"):
        db.add(SensorReading(sample_id=r["sample_id"], at=now - timedelta(minutes=int(r["minutes_ago"])), temp_c=float(r["temp_c"]), ambient_c=float(r["ambient_c"]), source="logger"))
    for r in _rows("weather.csv"):
        db.add(WeatherReading(station=r["station"], at=now - timedelta(hours=int(r["hours_ago"])), temp_c=float(r["temp_c"]), wind_kt=float(r["wind_kt"]),
                              gust_kt=float(r["gust_kt"]), wind_dir=int(r["wind_dir"]), vis_km=float(r["vis_km"]), pressure_hpa=float(r["pressure_hpa"])))
    for r in json.loads((settings.data_dir / "routes.json").read_text()):
        db.add(Route(id=r["id"], name=r["name"], kind=r["kind"], waypoints=r["waypoints"]))
    db.add(EnvLayer(name="seaice", updated_at=now - timedelta(hours=6), synthetic=True, note="Synthetic demo layer derived from distance to coast"))
    db.add(SyncState(id=1, clock=0))
    db.commit()
