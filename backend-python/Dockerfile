# Slim Python image — works the same on Docker Desktop (Windows + Mac).
# Build context is expected to be the REPO ROOT (not backend-python/), so both
# the Railway builder and `docker compose` can COPY the sibling config/ dir
# into the image alongside the app.
FROM python:3.12-slim

WORKDIR /app

# Install deps first so Docker layer cache stays useful when app code changes.
COPY backend-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend-python/app ./app
COPY config ./config

# Ship the EPA D6 RIN CSV inside the image as a seed. On first boot, if the
# mounted volume's epa/ dir is empty, code copies this seed onto the volume
# so a fresh Railway deploy has real RIN prices without any manual CLI upload.
# Subsequent CSV refreshes overwrite the volume file (see README).
COPY backend-python/data/epa /app/seed_data/epa

# Persistent state lives under /data so a mounted volume (Railway, docker-compose
# bind mount, k8s PVC) survives redeploys. APP_DATA_DIR points the app at it;
# code creates the DuckDB file + epa/ subdir on first boot.
ENV APP_DATA_DIR=/data \
    APP_CRUSH_MODEL_PATH=/app/config/crush_model.json
RUN mkdir -p /data/epa

EXPOSE 8000

# Bind to PORT when the host provides one (Railway, Heroku, Cloud Run), else
# fall back to 8000 for local docker + docker-compose. Shell form is needed
# for env-var expansion; exec form would treat ${PORT} as a literal string.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
