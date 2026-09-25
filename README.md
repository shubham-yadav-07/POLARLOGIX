# POLARLOGIX

Integrated polar expedition logistics, safety and GIS platform — built for **Smart India
Hackathon 2026, PS 26062** ("Integrated Polar Expedition Logistics and Asset Management
System").

A working FastAPI backend + a real offline-first web frontend (PWA), backed by
PostgreSQL (or SQLite for local dev). Field devices write to a local IndexedDB queue
first and sync to the server when a link is available — this is real, not simulated:
kill your network, make changes, reload the page, and they're still there.

---

## 1. What's real and what's a demo

Being upfront about this matters more than looking finished.

| Piece | Status |
|---|---|
| Backend (FastAPI, all endpoints below) | **Real**, tested |
| Database schema, sync engine, conflict rules | **Real**, tested (25 automated tests) |
| Offline queue (IndexedDB), service worker | **Real** — verified to survive a page reload while offline |
| Route-risk score, cold-chain forecast, SAR search grid | **Real computation**, server-side — but the *models* are simple, explainable prototypes, not validated against real incident data |
| Coastline / ice-shelf map layers | **Real** — Natural Earth 1:50m data, clipped and served as GeoJSON |
| Sea-ice concentration layer | **Synthetic** — a distance-from-coast approximation, clearly labelled as such in the API response. Swap in NSIDC/Copernicus data when available (see §7) |
| Personnel, assets, cargo, inventory, weather | **Synthetic demo data**, deterministically generated (`scripts/generate_data.py`), chosen so the numbers match a coherent story (37 personnel, 126 assets, 18 cargo items in transit) |
| Cargo rules (air weight limit, hazardous cargo) | Based on NCPOR's own ISEA expedition advertisements — see `data/cargo_rules.json` for the source and a `verified` flag on each rule |
| AI assistant | Retrieves real facts from the database and cites which tables it used; it does not call an external LLM. No safety decision is automated |
| SAR workflow | Decision-support simulation — explicitly not certified SAR software |

---

## 2. Run it locally (fastest path)

Requires Python 3.11+.

```bash
git clone <this-repo>
cd polarlogix
./scripts/run_dev.sh
```

That script creates a virtualenv, installs dependencies, generates the demo datasets
and the coastline GeoJSON on first run, and starts the server with auto-reload.

Open **http://localhost:8000** and sign in with:

| Username | Password | Role |
|---|---|---|
| `control` | `polar2026` | Mission manager |
| `leader` | `polar2026` | Station leader |
| `bravo` | `polar2026` | Field device, Team Bravo |
| `logistics` | `polar2026` | Logistics officer |

(Password is `polar2026` for all demo accounts unless you changed `DEMO_PASSWORD`.)

### Manual setup (if you don't want to use the script)

```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

python scripts/generate_data.py     # writes data/*.csv and data/cargo_rules.json
python scripts/build_geo.py         # downloads Natural Earth once, writes data/geo/*.geojson

cp .env.example .env                # edit if you want, defaults work for local dev
uvicorn app.main:app --reload
```

---

## 3. Run it with Docker (matches production)

```bash
docker compose up --build
```

This starts PostgreSQL and the API together. Open http://localhost:8000. To run just
the API image against your own database:

```bash
docker build -t polarlogix .
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/polarlogix \
  -e SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))") \
  polarlogix
```

---

## 4. Deploy it

### Render (one click, uses `render.yaml`)
1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at the repo. It reads `render.yaml` and
   creates a web service + managed PostgreSQL database automatically.
3. First boot seeds the demo dataset. Change `SEED_DEMO_DATA=false` in the Render
   dashboard once you have real data and set `ADMIN_USERNAME` / `ADMIN_PASSWORD` instead.

### Railway / Fly.io / any Docker host
The `Dockerfile` is standard — build it, set `DATABASE_URL` and `SECRET_KEY` as
environment variables, and run it. `/api/health` is a good health-check path.

### Plain VM (no Docker)
```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://...
export SECRET_KEY=...
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
# put nginx or Caddy in front for TLS
```

**Before any real deployment:**
- Generate a real `SECRET_KEY` (see `.env.example`).
- Set `SEED_DEMO_DATA=false` and create a real admin via `ADMIN_USERNAME`/`ADMIN_PASSWORD`,
  or seed your own data.
- Set `CORS_ORIGINS` if the frontend will be hosted on a different domain.
- Put the app behind HTTPS — the PWA service worker and secure cookies expect it.

---

## 5. Project layout

```
polarlogix/
├── app/
│   ├── main.py            FastAPI app, middleware, static file routes
│   ├── config.py          Settings from environment variables
│   ├── db.py               SQLAlchemy engine/session
│   ├── models.py           Database schema
│   ├── security.py         JWT auth, password hashing, role checks
│   ├── seed.py              Loads data/*.csv into the database on first boot
│   ├── audit.py             Audit-log helper
│   ├── serializers.py       DB row -> API JSON
│   ├── routers/             auth, ops (missions/assets/personnel/inventory), cargo, safety (risk/coldchain/sar), misc (dashboard/geo/sync/assistant/reports)
│   └── services/             geo, rules, inventory, coldchain, risk, sar, sync, alerts, assistant — the actual logic, unit-tested
├── static/                  The frontend: plain HTML/CSS/JS, no build step
│   ├── index.html / login.html
│   ├── css/app.css          Light + dark theme (data-theme attribute)
│   ├── js/api.js            Auth + fetch wrapper + theme toggle
│   ├── js/db.js              Real IndexedDB offline queue
│   ├── js/sync.js            Talks to /api/sync/push and /api/sync/pull
│   ├── js/map.js              Renders GeoJSON as a polar-stereographic SVG map
│   ├── js/app.js               All screen renderers
│   └── sw.js                  Service worker (offline app-shell caching)
├── data/                      Generated CSVs/JSON + geo/ (generated GeoJSON)
├── scripts/                   generate_data.py, build_geo.py, run_dev.sh, reset_db.py
├── tests/                      pytest suite (25 tests, logic + API)
├── docs/                       ARCHITECTURE.md, API.md, DATA.md
├── Dockerfile, docker-compose.yml, render.yaml
└── .github/workflows/ci.yml    Tests + Docker build on every push
```

---

## 6. Testing

```bash
pytest tests/ -q                       # 25 tests, SQLite, ~0.1s
TEST_DATABASE_URL=postgresql://... pytest tests/ -q   # same suite against PostgreSQL
```

Tests cover: cargo rules (hazard/air-limit logic), cold-chain forecasting (outlier
flagging, ETA calculation), route-risk scoring (monotonicity, band thresholds), the SAR
search-grid math (probability normalisation, wind-shift direction), geo helpers
(land/sea classification, distance), and dataset integrity (no hazardous cargo planned
by air, IDs unique, counts match the story).

---

## 7. Extending toward production

Ranked by what would matter most to a real deployment:

1. **Real sea-ice data.** Replace `app/services/geo.py::sea_ice()` with a sampler over
   NSIDC Sea Ice Index or Copernicus Marine data. The API shape (`/api/geo/seaice`)
   already returns a `synthetic: true` flag so the frontend can show a banner once this
   changes.
2. **Real personnel/asset/cargo data.** Replace the CSVs in `data/` with an import from
   NCPOR's actual records, or build an admin import screen.
3. **Full CRDT sync.** The current conflict model (last-write-wins + keep-both-for-safety-fields)
   is deliberately simple and explainable. Peer-to-peer sync between field devices
   (not just field ↔ HQ) is on the roadmap, not in this build.
4. **SAR grid validation.** The search-grid model is a wind-shifted Gaussian — a
   reasonable decision-support visual, but not a leeway/SAROPS model. Do not use it
   operationally without review by a SAR professional.
5. **LLM-backed assistant.** The assistant currently answers from a small set of
   database queries. An LLM could be added to rephrase answers, but the underlying facts
   should keep coming from the same tool calls, not the model's own knowledge.

See `docs/ARCHITECTURE.md` for the fuller picture and `docs/API.md` for the endpoint
reference.
