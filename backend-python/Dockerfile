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

# Persistent state lives under /data so a mounted volume (Railway, docker-compose
# bind mount, k8s PVC) survives redeploys. APP_DATA_DIR points the app at it;
# code creates the DuckDB file + epa/ subdir on first boot.
ENV APP_DATA_DIR=/data \
    APP_CRUSH_MODEL_PATH=/app/config/crush_model.json
RUN mkdir -p /data/epa

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
