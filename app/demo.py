"""Demo heartbeat: keeps the seeded field teams checking in so a long-running demo
deployment does not drift into a permanent 'missed check-in'. Off unless DEMO_MODE=true.
It is clearly labelled: check-ins carry device_id 'demo-heartbeat'."""
import asyncio
from datetime import timedelta
from uuid import uuid4

from .db import SessionLocal
from .models import Personnel, User, utcnow
from .services import sync


def beat() -> int:
    n = 0
    with SessionLocal() as db:
        user = db.query(User).filter(User.role == "manager").first()
        if not user:
            return 0
        now = utcnow()
        teams = {}
        for p in db.query(Personnel).all():
            teams.setdefault(p.team, []).append(p)
        for team, members in teams.items():
            if any(m.hold for m in members):
                continue
            if max(m.next_due_at for m in members) - now < timedelta(minutes=10):
                ev = sync.Ev(event_id=f"beat-{uuid4()}", type="CHECKIN", entity_id=team, payload={"team": team}, clock=sync.server_clock(db) + 1, created_at=now)
                sync._process(db, user, "demo-heartbeat", ev)
                n += 1
        db.commit()
    return n


async def loop(period_s: int = 60):
    while True:
        await asyncio.sleep(period_s)
        try:
            await asyncio.to_thread(beat)
        except Exception:      # never crash the app because of the heartbeat
            pass
