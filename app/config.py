"""Runtime settings, all from environment variables (see .env.example)."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'polarlogix.db'}")
    # Render / Heroku style URLs -> SQLAlchemy + psycopg 3
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings:
    database_url = _db_url()
    secret_key = os.getenv("SECRET_KEY", "dev-only-change-me-please-32-bytes-min")
    access_token_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "480"))
    refresh_token_days = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
    seed_demo_data = _bool("SEED_DEMO_DATA", True)
    demo_password = os.getenv("DEMO_PASSWORD", "polar2026")
    demo_mode = _bool("DEMO_MODE", False)          # background heartbeat that keeps demo teams checking in
    data_dir = pathlib.Path(os.getenv("DATA_DIR", str(ROOT / "data")))
    static_dir = pathlib.Path(os.getenv("STATIC_DIR", str(ROOT / "static")))
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    allow_link_sim = _bool("ALLOW_LINK_SIM", True)  # X-Link-Sim header slows /api/sync for demos


settings = Settings()
