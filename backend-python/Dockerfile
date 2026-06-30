# Slim Python image — works the same on Docker Desktop (Windows + Mac).
FROM python:3.12-slim

WORKDIR /app

# Install deps first so Docker layer cache stays useful when app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
