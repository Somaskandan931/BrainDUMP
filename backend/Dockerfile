# Build context is the REPO ROOT (not backend/), because backend/*.py does
# `from backend import config`-style absolute imports — the package has to
# be importable as `backend`, which only works if /app/backend exists.
#
# On Render: set dockerfilePath to backend/Dockerfile and dockerContext to
# the repo root (see render.yaml).

FROM python:3.11-slim

WORKDIR /app

# sentence-transformers / faiss-cpu / lightgbm / xgboost pull in compiled
# extensions that sometimes need a compiler on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY alembic.ini ./alembic.ini

ENV PYTHONUNBUFFERED=1
# BRAINDUMP_DATA_DIR should point at Render's persistent disk mount (see
# render.yaml) so SQLite survives deploys/restarts instead of living on
# the container's ephemeral filesystem.
ENV BRAINDUMP_DATA_DIR=/data

EXPOSE 8000

# Render sets $PORT; default 8000 covers local `docker run`.
# --proxy-headers: behind Render's proxy every request would otherwise appear to come
# from the proxy's IP, collapsing the per-IP login/register rate limits
# (backend/auth/rate_limit.py) into one shared bucket. The container is only
# reachable through that proxy, so trusting its forwarded headers is safe here.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
