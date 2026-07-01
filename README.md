# IBM-Bob-Hackathon — Ethanol Crush Margin Dashboard

Decision-support dashboard for corn ethanol crush margins, z-scores, and warning signals.

## Run locally

**Backend** (`backend-python`, port 8000):

With Docker from project root:

```bash
docker compose up
```

Or without Docker:

```bash
cd backend-python
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # add APP_EIA_API_KEY (optional)
uvicorn app.main:app --reload --port 8000
```

**Frontend** (`client-react-vite`, port 5173):

```bash
cd client-react-vite
npm install
npm run dev
```

Start the backend first. Vite proxies `/api` to `localhost:8000`.

## Daily ingestion

```bash
cd backend-python
.venv\Scripts\python scripts/run_daily_ingest.py
```

Protected manual trigger: `POST /api/admin/ingest` with header `Authorization: Bearer <APP_ADMIN_TOKEN>`.

## Tests

```bash
cd backend-python
.venv\Scripts\pytest -q
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
