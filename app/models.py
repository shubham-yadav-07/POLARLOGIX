"""Database schema. All datetimes are naive UTC (see utcnow / iso)."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(120))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))          # manager | leader | field | logistics
    station: Mapped[str] = mapped_column(String(60), default="")


class Station(Base):
    __tablename__ = "stations"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(30))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    approx: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(200), default="")


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    org: Mapped[str] = mapped_column(String(160), default="")
    base: Mapped[str] = mapped_column(String(60))
    destination: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    risk_rating: Mapped[str] = mapped_column(String(12), default="MEDIUM")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[str] = mapped_column(String(12), default="")
    end_date: Mapped[str] = mapped_column(String(12), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    permit_valid_until: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    route_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)


class Personnel(Base):
    __tablename__ = "personnel"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(60))
    team: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[Optional[str]] = mapped_column(ForeignKey("missions.id"), nullable=True)
    station: Mapped[str] = mapped_column(String(40))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    checkin_interval_min: Mapped[int] = mapped_column(Integer, default=180)
    last_checkin_at: Mapped[datetime] = mapped_column(DateTime)
    next_due_at: Mapped[datetime] = mapped_column(DateTime)
    hold: Mapped[bool] = mapped_column(Boolean, default=False)      # demo: scenario keeps the team "silent"


class Checkin(Base):
    __tablename__ = "checkins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team: Mapped[str] = mapped_column(String(40), index=True)
    personnel_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    device_id: Mapped[str] = mapped_column(String(60), default="HQ")
    source: Mapped[str] = mapped_column(String(20), default="user")
    event_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(30), index=True)
    station: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="Available")
    level_pct: Mapped[int] = mapped_column(Integer, default=100)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    mission_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CargoItem(Base):
    __tablename__ = "cargo_items"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    consignment: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(80))
    weight_kg: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(20), default="")
    hazard: Mapped[bool] = mapped_column(Boolean, default=False)
    route: Mapped[str] = mapped_column(String(10))            # air | ship
    current_node: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="packed")   # packed | in_transit | delivered


class CargoHandoff(Base):
    __tablename__ = "cargo_handoffs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cargo_id: Mapped[str] = mapped_column(ForeignKey("cargo_items.id"), index=True)
    from_node: Mapped[str] = mapped_column(String(60))
    to_node: Mapped[str] = mapped_column(String(60))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    username: Mapped[str] = mapped_column(String(60), default="")
    device_id: Mapped[str] = mapped_column(String(60), default="HQ")
    event_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(20))
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    daily_use: Mapped[float] = mapped_column(Float)
    min_qty: Mapped[float] = mapped_column(Float)
    station: Mapped[str] = mapped_column(String(40))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    delta: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(120), default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    device_id: Mapped[str] = mapped_column(String(60), default="HQ")
    event_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    container_id: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(160), default="")
    limit_c: Mapped[float] = mapped_column(Float, default=-15.0)
    mission_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id"))
    at: Mapped[datetime] = mapped_column(DateTime)
    temp_c: Mapped[float] = mapped_column(Float)
    ambient_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="logger")   # logger | field | simulated
    __table_args__ = (Index("ix_sensor_sample_at", "sample_id", "at"),)


class WeatherReading(Base):
    __tablename__ = "weather_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime)
    temp_c: Mapped[float] = mapped_column(Float)
    wind_kt: Mapped[float] = mapped_column(Float)
    gust_kt: Mapped[float] = mapped_column(Float)
    wind_dir: Mapped[int] = mapped_column(Integer)
    vis_km: Mapped[float] = mapped_column(Float)
    pressure_hpa: Mapped[float] = mapped_column(Float)
    __table_args__ = (Index("ix_weather_station_at", "station", "at"),)


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))
    waypoints: Mapped[list] = mapped_column(JSON)


class EnvLayer(Base):
    __tablename__ = "env_layers"
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(200), default="")


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    team: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20), default="OPEN")      # OPEN | DISPATCHED | CLOSED
    severity: Mapped[str] = mapped_column(String(10), default="high")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_lat: Mapped[float] = mapped_column(Float)
    last_lon: Mapped[float] = mapped_column(Float)
    overdue_min: Mapped[int] = mapped_column(Integer, default=0)
    weather: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    resources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    grid: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class IncidentAction(Base):
    __tablename__ = "incident_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(String(300), default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncEvent(Base):
    __tablename__ = "sync_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    device_id: Mapped[str] = mapped_column(String(60), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    payload: Mapped[dict] = mapped_column(JSON)
    clock: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)              # device time
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(12), default="accepted")  # accepted | rejected | conflict
    reason: Mapped[str] = mapped_column(String(240), default="")


class FieldVersion(Base):
    """Last writer per (entity, id, field): used for last-write-wins and conflict detection."""
    __tablename__ = "field_versions"
    entity: Mapped[str] = mapped_column(String(30), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    field: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)                           # {"v": <value>}
    clock: Mapped[int] = mapped_column(Integer, default=0)
    device_id: Mapped[str] = mapped_column(String(60), default="HQ")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncConflict(Base):
    __tablename__ = "sync_conflicts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(60))
    field: Mapped[str] = mapped_column(String(40))
    server_value: Mapped[dict] = mapped_column(JSON)
    device_value: Mapped[dict] = mapped_column(JSON)
    server_clock: Mapped[int] = mapped_column(Integer)
    device_clock: Mapped[int] = mapped_column(Integer)
    server_device: Mapped[str] = mapped_column(String(60), default="HQ")
    device_id: Mapped[str] = mapped_column(String(60))
    event_id: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10), default="open")    # open | resolved
    resolution: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)   # server | device
    resolved_by: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncState(Base):
    __tablename__ = "sync_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clock: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
