#!/usr/bin/env bash
# Quick local start: creates a venv if missing, installs deps, runs the seed data
# generator + geo builder if needed, then starts the API with auto-reload.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements-dev.txt

if [ ! -f data/cargo_rules.json ]; then
  echo "Generating synthetic datasets..."
  python scripts/generate_data.py
fi
if [ ! -f data/geo/coastline.geojson ]; then
  echo "Building coastline GeoJSON (downloads Natural Earth data once)..."
  python scripts/build_geo.py
fi

export DATABASE_URL="${DATABASE_URL:-sqlite:///./polarlogix.db}"
export SECRET_KEY="${SECRET_KEY:-dev-only-change-me-please-32-bytes-min}"
echo "Starting POLARLOGIX on http://localhost:8000  (demo login: control / polar2026)"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
