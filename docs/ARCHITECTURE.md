# Architecture

## Shape

```
Browser (PWA)                         FastAPI (app/)                  Database
─────────────                         ───────────────                 ────────
index.html / login.html
  ├─ api.js    (auth, fetch wrapper)  routers/
  ├─ db.js     (IndexedDB queue)  ──▶   auth.py        login/refresh
  ├─ sync.js   (push/pull)       ──▶   ops.py          missions, assets, personnel, inventory
  ├─ map.js    (GeoJSON -> SVG)  ──▶   cargo.py        cargo, handoffs, rules
  └─ app.js    (all screens)     ──▶   safety.py       risk, cold-chain, SAR, weather
sw.js (service worker,                misc.py          dashboard, geo, sync, assistant, reports
  caches the app shell)                    │
                                       services/         (the actual logic, unit-tested)
                                         geo.py            projection, land/sea, sea-ice (synthetic)
                                         rules.py           cargo/hazard rules
                                         inventory.py        days-left, 5-day survival check
                                         coldchain.py         outlier flagging + ETA forecast
                                         risk.py               explainable route-risk score
                                         sar.py                 missed-checkin -> incident -> search grid
                                         sync.py                 event processing, conflict rules
                                         alerts.py                derives dashboard alerts from live data
                                         assistant.py              records-only Q&A
```

## Data flow for one field action (e.g. a check-in)

1. Browser calls `queueOrSend()` in `app.js`.
2. `db.js` writes the event to IndexedDB immediately (`status: pending`). The UI updates
   right away — it does not wait for the network.
3. If online, `sync.js` immediately pushes the queue to `POST /api/sync/push`.
4. The backend (`services/sync.py`) validates the event's role, applies the type-specific
   handler (`_h_checkin`, `_h_handoff`, `_h_stock`, `_h_reading`, `_h_edit`,
   `_h_asset_add`), and returns a per-event result: `accepted`, `duplicate`, `rejected`,
   or `conflict`.
5. The device marks each event `synced` or `conflict` in IndexedDB.
6. If offline, the event just stays `pending`. Reloading the page does not lose it —
   IndexedDB is durable browser storage, not memory.
7. When the link returns, the `online` browser event triggers an automatic sync.

## Conflict handling

Two kinds of fields:

- **Ordinary fields** (asset status, mission progress, etc.): last-write-wins, ordered
  by `(logical_clock, device_id)`. See `FieldVersion` in `models.py`.
- **Safety fields** (currently `inventory.qty`, `inventory.min_qty` — see
  `sync.py::SAFETY_FIELDS`): if the server's value changed since this device's last
  sync, *both* values are kept. A row is written to `sync_conflicts` and the change is
  **not** applied automatically. An operator resolves it from the "Offline Sync" screen
  (`POST /api/sync/conflicts/{id}/resolve`), and that resolution is written to the audit
  log.

Every accepted or conflicting event is also recorded in `sync_events` with the raw
payload, so the full history can be replayed or audited (`GET /api/sync/log`,
`GET /api/reports/sync-events.csv`).

## Why SQLite locally and PostgreSQL in production

SQLite is zero-setup for local development and CI. PostgreSQL is what
`docker-compose.yml` and `render.yaml` use for anything resembling a real deployment,
because it handles concurrent writes from multiple field devices correctly. The code
is unchanged between the two — only `DATABASE_URL` differs — and the test suite can run
against either (see `tests/conftest.py`).

## Explainability by design

Two places deliberately expose their internals instead of returning a bare number:

- **Route risk** (`services/risk.py::compute`) returns every weighted component
  (`ice`, `wind`, `visibility`, `distance`, `data_age`) alongside the final score, plus a
  one-line `why` naming the largest contributor.
- **Cold-chain forecast** (`services/coldchain.py::analyze`) returns the raw readings,
  the filtered (outlier-robust) series, which points were flagged as outliers, and the
  fitted warming rate — so a reviewer can see why an ETA was predicted, not just the ETA
  itself.
