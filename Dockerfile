# POLARLOGIX API + static frontend, single container.
FROM python:3.12-slim AS base

# System deps needed by shapely (GEOS) and psycopg (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-c1v5 libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY data ./data
COPY scripts ./scripts

ENV DATA_DIR=/app/data \
    STATIC_DIR=/app/static \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Runs as a plain user, not root
RUN useradd -m polarlogix && chown -R polarlogix:polarlogix /app
USER polarlogix

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
