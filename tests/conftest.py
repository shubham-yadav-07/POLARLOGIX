import os
import tempfile

# Must be set before the app is imported. Run against PostgreSQL with TEST_DATABASE_URL=postgresql://...
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["DEMO_MODE"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-with-more-than-32-bytes!!"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.seed import init_db


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "polar2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def manager(client):
    return _login(client, "control")


@pytest.fixture()
def field(client):
    return _login(client, "bravo")


@pytest.fixture()
def logistics(client):
    return _login(client, "logistics")


def make_event(type_, entity_id, payload, clock=1, base_clock=0, event_id=None, created_at=None):
    from uuid import uuid4
    from datetime import datetime, timezone
    return {"event_id": event_id or str(uuid4()), "type": type_, "entity_id": entity_id, "payload": payload, "clock": clock,
            "base_clock": base_clock, "created_at": created_at or datetime.now(timezone.utc).isoformat()}


def push(client, headers, events, device="TAB-TEST"):
    r = client.post("/api/sync/push", json={"device_id": device, "events": events}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
