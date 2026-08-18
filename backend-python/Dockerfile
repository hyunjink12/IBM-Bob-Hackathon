# Slim Python image — works the same on Docker Desktop (Windows + Mac).
FROM python:3.12-slim

WORKDIR /app

# Install deps first so Docker layer cache stays useful when app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Persistent state lives under /data so a mounted volume (Railway, docker-compose
# bind mount, k8s PVC) survives redeploys. APP_DATA_DIR points the app at it;
# code creates the DuckDB file + epa/ subdir on first boot.
ENV APP_DATA_DIR=/data
RUN mkdir -p /data/epa

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
