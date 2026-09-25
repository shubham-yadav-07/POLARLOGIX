"""POLARLOGIX API + static web app (one process)."""
import asyncio
import zlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import demo
from .config import settings
from .db import SessionLocal
from .routers import auth, cargo, misc, ops, safety
from .seed import init_db

VERSION = "1.0.0"
MAX_BODY = 2_000_000


class GzipRequestMiddleware:
    """Accept `Content-Encoding: gzip` request bodies (the field client compresses sync batches)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or dict(scope["headers"]).get(b"content-encoding") != b"gzip":
            return await self.app(scope, receive, send)
        body = b""
        while True:
            msg = await receive()
            body += msg.get("body", b"")
            if not msg.get("more_body"):
                break
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            data = d.decompress(body, MAX_BODY)
        except zlib.error:
            return await JSONResponse({"detail": "Bad gzip body"}, status_code=400)(scope, receive, send)
        if d.unconsumed_tail:
            return await JSONResponse({"detail": "Body too large"}, status_code=413)(scope, receive, send)
        headers = [(k, v) for k, v in scope["headers"] if k not in (b"content-encoding", b"content-length")] + [(b"content-length", str(len(data)).encode())]
        sent = False

        async def receive2():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": data, "more_body": False}
            return {"type": "http.disconnect"}
        await self.app(dict(scope, headers=headers), receive2, send)


class LinkSimMiddleware:
    """Demo helper: with header `X-Link-Sim: sat`, /api/sync requests are delayed like a ~1 KB/s satellite link."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and settings.allow_link_sim and scope["path"].startswith("/api/sync"):
            h = dict(scope["headers"])
            if h.get(b"x-link-sim") == b"sat":
                size = int(h.get(b"content-length", b"0") or 0)
                await asyncio.sleep(min(6.0, 0.4 + size / 1024))
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(demo.loop()) if settings.demo_mode else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="POLARLOGIX", version=VERSION, description="Integrated polar expedition logistics, safety and GIS platform (SIH 2026, PS 26062).", lifespan=lifespan)
app.add_middleware(LinkSimMiddleware)
app.add_middleware(GzipRequestMiddleware)
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, ops.router, cargo.router, safety.router, misc.router):
    app.include_router(r)


@app.get("/api/health", tags=["platform"])
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
        ok = True
    except Exception:
        ok = False
    return JSONResponse({"status": "ok" if ok else "db_error", "version": VERSION, "db": "sqlite" if settings.database_url.startswith("sqlite") else "postgresql", "demo_mode": settings.demo_mode}, status_code=200 if ok else 503)


app.mount("/static", StaticFiles(directory=str(settings.static_dir), check_dir=False), name="static")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(settings.static_dir / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(settings.static_dir / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/login.html", include_in_schema=False)
def login_page():
    return FileResponse(settings.static_dir / "login.html", headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(settings.static_dir / "index.html", headers={"Cache-Control": "no-cache"})
