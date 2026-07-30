# IBM-Bob-Hackathon — Ethanol Crush Margin Dashboard

Decision-support dashboard for corn ethanol crush margins, z-scores, and warning signals.

## Run locally

You need two processes: the FastAPI backend (port 8000) and the Vite dev server (port 5173). Start the backend first — Vite proxies `/api` to `localhost:8000`, so the frontend needs it up before it can render live data.

### 1. Backend

```bash
cd backend-python
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Open `backend-python/.env` and paste in an EIA API key. Free registration at https://www.eia.gov/opendata/register.php — the key is emailed instantly. Without it, ethanol production + stocks fall back to synthetic seed data and the orange "SYNTHETIC SEED DATA" banner stays up. Everything else (corn, ethanol price, DDGS, nat gas, RBOB) comes from Yahoo Finance and works without any key.

Then boot the server:

```bash
uvicorn app.main:app --reload --port 8000
```

First launch takes 10–30 seconds while it seeds the DuckDB store and pulls Yahoo + EIA. Watch for `Application startup complete.` in the terminal.

**Docker alternative** (from project root, skip the venv steps):

```bash
docker compose up
```

### 2. Frontend

In a second terminal:

```bash
cd client-react-vite
npm install
npm run dev
```

Vite prints the actual URL it bound to — usually `http://localhost:5173`, but **if 5173 is already in use it silently picks 5174, 5175, …** so read the terminal, don't assume. Open that URL in the browser.

### Notice

- **"SYNTHETIC SEED DATA" banner won't go away after adding the EIA key.** The backend loads `.env` once at startup — restart the uvicorn process after editing `.env`. If the banner still shows, hit `POST /api/admin/ingest` (see below) or restart with an empty `data/` folder.
- **Yahoo Finance rate limits.** Repeatedly restarting the backend can trip Yahoo's per-IP throttle. Symptoms: `Error fetching ZC=F: Too Many Requests` in the terminal. Not fatal — the app keeps serving whatever prices are already in DuckDB. Wait 15–60 minutes or switch networks (e.g. phone hotspot) for a fresh IP.
- **Port 8000 collides with Docker Desktop.** If Docker is running, it may hold port 8000. Quit Docker or run the backend on a different port and update `VITE_API_BASE_URL` accordingly.

## Daily ingestion

```bash
cd backend-python
.venv/bin/python scripts/run_daily_ingest.py    # Windows: .venv\Scripts\python
```

Or trigger it against a running backend:

```bash
curl -X POST http://localhost:8000/api/admin/ingest \
  -H "Authorization: Bearer $APP_ADMIN_TOKEN"
```

## Tests

```bash
cd backend-python
.venv/bin/pytest -q                             # Windows: .venv\Scripts\pytest
```

## Deploy (public demo)

- **Frontend**: Vercel — set `VITE_API_BASE_URL` to the backend URL.
- **Backend**: Railway / Render / Fly.io with persistent volume for `backend-python/data/`.
- Copy `backend-python/.env.example` → `.env` and set `APP_EIA_API_KEY`, `APP_ADMIN_TOKEN`.

## Config

| File | Purpose |
|------|---------|
| `config/crush_model.json` | CARD yields and misc opex |
| `client-react-vite/src/config/dashboard_config.js` | Z-score window, chart range, tooltips |
| `backend-python/.env` | Secrets only (EIA key, admin token) |
