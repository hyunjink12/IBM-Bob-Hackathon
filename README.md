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

## Refreshing D6 RIN prices  - MANUAL WEEKLY STEP

**This is the only recurring manual step in the whole pipeline.** Everything else — Yahoo futures, EIA weekly, CFTC COT — refreshes automatically on ingest. D6 RIN prices come from a JavaScript-rendered EPA dashboard that has no clean API, so the workflow is: download CSV → overwrite the same file path → trigger ingest.

D6 RIN revenue is a first-class margin driver — at current prices it's often the largest single revenue line in the crush margin, larger than the ethanol sale itself. Skipping this refresh means the app forward-fills a stale RIN price and the margin drifts from reality.

**Weekly workflow:**

1. Open [EPA's RIN Trades and Price Information dashboard](https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information).
2. Select the **RIN Price Data** view from the dropdown.
3. Multi-select all **Transfer Years** (click first year, Shift-click last year).
4. Keep **Fuel (D Code)** set to `D6`.
5. Click **Export Table** — downloads a CSV.
6. **Overwrite** `backend-python/data/epa/rin_prices.csv` with the fresh download. **Keep the same filename** — the app watches that specific path.
7. Trigger ingest so the app re-parses the file:
   ```bash
   curl -X POST http://localhost:8000/api/admin/ingest -H "Authorization: Bearer $APP_ADMIN_TOKEN"
   ```
   Or restart the backend — startup runs the pipeline automatically.

The `EpaRinFileClient` filters the CSV down to canonical rows (RIN Year == Transfer Year AND QAP Service Type == "Unverified") and upserts them tagged `source="epa_emts"`. Old EPA rows are replaced; existing Yahoo/EIA data is untouched. If the CSV is missing entirely, the RIN revenue line drops out of the margin composition and the RIN card shows `—`; everything else keeps working.

## Blending economics

The bottom of the Market Overview panel shows a derived-signal card labelled **Blending Economics**. It is not a raw price — it is the number that determines whether a refiner blends more ethanol at the margin, above and beyond the RFS mandate.

**Formula:**

```
blender_advantage_$/gal  =  RBOB_$/gal  −  (ethanol_$/gal  −  D6_RIN_$/gal)
                                            └─── effective ethanol cost ──┘
```

**Why the RIN credit is subtracted:** the refiner captures the D6 RIN when they blend the ethanol into gasoline (they can either use it toward their own RFS obligation or sell it to another obligated party). So the refiner's *effective* cost per gallon of ethanol is the physical wholesale price minus the value of the RIN they get back. At current RIN prices, this subtraction is large — a $2.60 physical ethanol print net of a $1.99 D6 RIN gives an effective cost of $0.61/gal, well below RBOB.

**Interpretation:**

- **Positive advantage** → ethanol is a cheaper blendstock than gasoline after RIN credit → refiners push blend rates up toward the E10/E15 ceiling.
- **Negative advantage** → ethanol is more expensive than the RBOB it displaces → refiners blend only to hit the RFS mandate floor.

**Regime bands (`indifference_band_usd_per_gallon`):** the card labels regimes as *Blenders favor ethanol / Blend indifference / Blenders resist ethanol* using a placeholder ±$0.30/gal indifference band around zero. **This threshold is not derived from a historical distribution of the spread** — it is a reasonable-magnitude guess based on typical blending logistics cost. A serious desk would replace it with the 20th/80th percentile of the historical `blender_advantage` series (same pattern as the warning rules). Tune the constant `_BLENDING_INDIFFERENCE_BAND_USD` in `backend-python/app/managers/dashboard_manager.py` if you have a better anchor.

**Known simplifications:** the calculation uses front-month CBOT RBOB and CME EH ethanol — not physical rack prices at a specific terminal. A real desk would layer in freight to the blending point, denaturant cost (~$0.05–0.10/gal), and terminal-specific basis. The current number is a national indicative signal, not a specific blender's P&L.

## Crush margin formulas

The dashboard displays two related but different numbers. Know which one you're looking at.

**Full plant crush margin (per bushel of corn)** — what the dry-mill actually earns:

```
margin_per_bushel =
    (ethanol_$/gal × 2.8)              # ethanol revenue
  + (DDGS_$/short_ton × 17 ÷ 2000)     # DDGS coproduct revenue
  + (corn_oil_$/lb × 0.7)              # corn oil coproduct revenue
  + (d6_rin_$/gal × 2.8)               # D6 RIN revenue (1 RIN per gal ethanol)
  − corn_$/bu                          # feedstock cost
  − (nat_gas_$/MMBtu × 0.0728)         # process energy cost
  − 0.35                               # misc opex placeholder

margin_per_gallon = margin_per_bushel ÷ 2.8
```

Constants live in [`config/crush_model.json`](config/crush_model.json) and follow the Iowa State CARD dry-mill archetype. Coproduct and RIN lines drop out cleanly (revenue = 0) when the underlying price is missing on the merged daily row.

**CME-standard ethanol crush spread (physical only)** — the exchange-listed input dislocation gauge:

```
crush_spread_$/bu = (ethanol_$/gal × 2.8) − corn_$/bu
```

No coproducts, no costs, no RIN. Matches CBOT `2.8 × EH − ZC`. This is the number a paper trader hedges; it's not the plant's P&L.

## Tests

```bash
cd backend-python
.venv/bin/pytest -q                             # Windows: .venv\Scripts\pytest
```

## Deploy (public demo)

- **Frontend**: Vercel — root directory `client-react-vite/`. Set `VITE_API_BASE_URL` to the backend URL (no trailing slash).
- **Backend**: Railway — repo picks up `railway.json` + `backend-python/Dockerfile` automatically.
  1. In Railway → **Volumes** → attach a volume to the service and set the mount path to `/data`.
  2. In **Variables**, set `APP_EIA_API_KEY`, `APP_ADMIN_TOKEN`, `APP_WATSONX_API_KEY`, `APP_WATSONX_PROJECT_ID`. `APP_DATA_DIR=/data` is already baked into the Dockerfile.
  3. After first deploy, drop a fresh EPA D6 CSV into the volume at `/data/epa/rin_prices.csv` (Railway CLI: `railway run --service backend -- bash -c "cat > /data/epa/rin_prices.csv" < rin_prices.csv`). The DuckDB file lives beside it at `/data/ethanol_dashboard.duckdb` and persists across redeploys.
- Overrides: `APP_DUCKDB_PATH` and `APP_EPA_RIN_CSV_PATH` still work if you want to relocate individual files.

## Config

| File | Purpose |
|------|---------|
| `config/crush_model.json` | CARD yields and misc opex |
| `config/wasde_schedule.json` | USDA-published WASDE release dates (see caveat below) |
| `client-react-vite/src/config/dashboard_config.js` | Z-score window, chart range, tooltips |
| `backend-python/.env` | Secrets only (EIA key, admin token, watsonx credentials) |
| `backend-python/data/epa/rin_prices.csv` | EPA D6 RIN weekly prices — **overwrite weekly** (see "Refreshing D6 RIN prices" above). In prod, lives at `$APP_DATA_DIR/epa/rin_prices.csv` on the mounted volume. |

## Data caveats

Release schedules the tape and countdown surface:

- **EIA WPSR** — hardcoded rule: Wednesday 10:30 AM ET. Does not model the Thursday shift that happens ~5×/year when Monday is a federal holiday.
- **CFTC COT** — hardcoded rule: Friday 3:30 PM ET. Same holiday-shift caveat.
- **USDA WASDE** — loaded from `config/wasde_schedule.json`, which ships prefilled with the 2026 published dates. When the file has no entry for the target month (e.g. you're asking about a date past the last row), the manager falls back to a "second Tuesday of the month at 12:00 ET" approximation and flags the resulting release with `is_approximate=true`. The tape renders an amber `≈` badge next to any approximate countdown so it's visible at a glance. **Verify the shipped dates against the official USDA calendar at https://www.usda.gov/oce/commodity/wasde before showing this to anyone whose job depends on it**, and update the JSON file annually after USDA publishes the next year's schedule.

Both hardcoded release rules (EIA, COT) and the WASDE approximation are honest fallbacks — not something to rely on when a real trading decision depends on the exact minute.
