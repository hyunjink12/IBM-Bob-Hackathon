# IBM-Bob — Ethanol Crush Margin Dashboard

Decision-support dashboard for corn ethanol crush margins, z-scores, and warning signals.

## How IBM Bob was used

IBM Bob (IBM's AI coding agent) built this dashboard throughout the hackathon; the IBM AI in the live product is **IBM Granite on watsonx.ai**. All numbers — crush margin, z-score, signal label, warning rules, inventory stress — are computed in Python. Granite takes that snapshot and writes a short trader briefing: what the margin signal means right now, which warnings are active, how those rules have performed historically, and one thing to watch. It shows up as the **Signal Briefing** strip at the top of the dashboard (optional — set `APP_WATSONX_API_KEY` and `APP_WATSONX_PROJECT_ID` in `.env`; without them the rest of the app is unchanged).

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

For the Granite **Signal Briefing** strip, also set `APP_WATSONX_API_KEY` and `APP_WATSONX_PROJECT_ID` (IBM Cloud IAM key + watsonx.ai project ID). Without them the dashboard still works; the briefing strip simply does not appear.

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
- **Signal Briefing 404s (`model_not_supported`).** IBM rotates watsonx.ai model IDs periodically — older Granite models get withdrawn as new ones ship. If the briefing endpoint returns a 404 saying the model was not found, deprecated, or removed, the hardcoded model ID needs to be bumped to whatever Granite instruct model is currently available on your watsonx region. List what your region supports with the snippet below (needs `APP_WATSONX_API_KEY` and `APP_WATSONX_URL` in `.env`), then update the two references at `backend-python/app/core/app_settings.py` (`watsonx_model_id`) and `backend-python/app/clients/watsonx_client.py` (`model_id` default) and restart the backend:

  ```bash
  cd backend-python && source .venv/bin/activate && python -c "
  import httpx
  from dotenv import dotenv_values
  env = dotenv_values('.env')
  r = httpx.post('https://iam.cloud.ibm.com/identity/token',
      data={'grant_type': 'urn:ibm:params:oauth:grant-type:apikey', 'apikey': env['APP_WATSONX_API_KEY']}, timeout=30)
  token = r.json()['access_token']
  r = httpx.get(f\"{env.get('APP_WATSONX_URL', 'https://us-south.ml.cloud.ibm.com')}/ml/v1/foundation_model_specs?version=2024-05-01&limit=200\",
      headers={'Authorization': f'Bearer {token}'}, timeout=30)
  for m in sorted(r.json().get('resources', []), key=lambda x: x['model_id']):
      if 'granite' in m['model_id'].lower():
          states = ','.join(str(l.get('id')) for l in m.get('lifecycle', []))
          print(f\"{m['model_id']}  [{states}]\")
  "
  ```

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

## Refreshing D6 RIN prices

The dashboard's margin math includes D6 RIN revenue (typically $1–2/bu at current prices — a real chunk of plant P&L). Prices come from EPA's public [RIN Trades and Price Information dashboard](https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information) via a manual weekly refresh:

1. Open the EPA page linked above and select the **RIN Price Data** view from the dropdown.
2. Multi-select all **Transfer Years** (click first year, Shift-click last year).
3. Keep **Fuel (D Code)** set to `D6`.
4. Click **Export Table** — downloads a CSV.
5. Overwrite `backend-python/data/epa/rin_prices.csv` with the fresh download (keep the same filename).
6. Trigger an ingest (`curl -X POST http://localhost:8000/api/admin/ingest -H "Authorization: Bearer $APP_ADMIN_TOKEN"` or restart the backend). The `EpaRinFileClient` parses the file, keeps only current-vintage Unverified D6 rows, and upserts them.

No network call — this is a file-drop pattern. Cadence is up to you; EPA publishes new prints weekly. If the CSV is missing, the RIN revenue line drops out of the margin composition and the RIN card shows a dash, everything else keeps working.

## Tests

```bash
cd backend-python
.venv/bin/pytest -q                             # Windows: .venv\Scripts\pytest
```

## Deploy (public demo)

- **Frontend**: Vercel — set `VITE_API_BASE_URL` to the backend URL.
- **Backend**: Railway / Render / Fly.io with persistent volume for `backend-python/data/`.
- Copy `backend-python/.env.example` → `.env` and set `APP_EIA_API_KEY`, `APP_ADMIN_TOKEN`, and (for the briefing strip) `APP_WATSONX_API_KEY`, `APP_WATSONX_PROJECT_ID`.

## Config

| File | Purpose |
|------|---------|
| `config/crush_model.json` | CARD yields and misc opex |
| `config/wasde_schedule.json` | USDA-published WASDE release dates (see caveat below) |
| `client-react-vite/src/config/dashboard_config.js` | Z-score window, chart range, tooltips |
| `backend-python/.env` | Secrets only (EIA key, admin token, watsonx credentials) |

## Data caveats

Release schedules the tape and countdown surface:

- **EIA WPSR** — hardcoded rule: Wednesday 10:30 AM ET. Does not model the Thursday shift that happens ~5×/year when Monday is a federal holiday.
- **CFTC COT** — hardcoded rule: Friday 3:30 PM ET. Same holiday-shift caveat.
- **USDA WASDE** — loaded from `config/wasde_schedule.json`, which ships prefilled with the 2026 published dates. When the file has no entry for the target month (e.g. you're asking about a date past the last row), the manager falls back to a "second Tuesday of the month at 12:00 ET" approximation and flags the resulting release with `is_approximate=true`. The tape renders an amber `≈` badge next to any approximate countdown so it's visible at a glance. **Verify the shipped dates against the official USDA calendar at https://www.usda.gov/oce/commodity/wasde before showing this to anyone whose job depends on it**, and update the JSON file annually after USDA publishes the next year's schedule.

Both hardcoded release rules (EIA, COT) and the WASDE approximation are honest fallbacks — not something to rely on when a real trading decision depends on the exact minute.
