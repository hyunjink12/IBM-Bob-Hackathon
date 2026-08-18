# Session Handoff — Ask Granite, RIN Pipeline, Blending Economics

Self-contained handoff so a fresh session can pick up without re-deriving decisions. Companion to [`RIN_INSIGHT_HANDOFF.md`](RIN_INSIGHT_HANDOFF.md) (which is thematic to the "RIN share of margin" stat idea) and the [`README`](README.md) (which is user-facing).

Read this end-to-end before starting new work.

---

## 1. What's in the app now

### Six Ask Granite chips (2-column grid, 3 rows)

```
[ EIA weekly     ] [ WASDE monthly  ]
[ COT positioning ] [ RIN market     ]
[ Policy         ] [ Margin drivers ]
```

Every chip has both a Granite-narrated answer AND a viz component. Chips are compact (font 0.76rem, 0.3×0.6rem padding) so the sidebar stays short. Order is intentional: agency releases → positioning → synthesis.

| Chip | Prose source | Viz |
|---|---|---|
| EIA weekly | EIA weekly stocks + production, last 4 prints | Dual sparkline (stocks blue, production orange) |
| WASDE monthly | USDA WASDE corn-for-ethanol + revision trend + next release | 6-report bar chart, blue latest |
| COT positioning | CFTC managed money net + 5Y percentile + WoW | Small MM net bar chart |
| RIN market | D6 RIN price + 5Y percentile + RIN share of margin | 4-week sparkline with %ile label |
| Policy | Latest 3 EPA RFS Federal Register documents + market lens | **Hyperlinked doc list** (date + type badge + clickable title) |
| Margin drivers | Ranked contribution list + ranked 4-week price moves | Diverging bar chart, 4-week % change |

### Blending Economics card (bottom of Market Overview)

Full-width centered card (`max-width: 720px, margin: 0 auto`) with:
- Big value: **blender's advantage after RIN credit** = `RBOB − (ethanol − D6 RIN)`
- Regime signal chip using app-wide `.signal--rich` / `--weak` / `--normal` classes: `FAVOR ETHANOL` / `RESIST ETHANOL` / `INDIFFERENT`
- 1Y sparkline of the same spread with dashed zero axis, blue area fill, latest-point dot
- 1Y percentile of the current advantage
- Subtle monospace footer: `RBOB $X.XX · ethanol $X.XX · D6 RIN $X.XX`

At current numbers: `+$2.49/gal` advantage means blenders push ethanol usage hard (RIN credit effectively makes ethanol a $0.49 blendstock competing against $3 RBOB).

### D6 RIN Price card (Market Overview grid)

Standard metric card with stale badge. Data source is the EPA Federal Register CSV workflow described in the README.

### Signal Briefing (top)

Unchanged in concept. Now hidden-warns cleanly when watsonx is unavailable; caching still keyed on `ingest_cache_key`.

---

## 2. Data pipeline changes

Three new / changed sources since the last handoff:

### D6 RIN prices — EPA file-drop

- **Source:** EPA EMTS RIN Trades and Price Information dashboard (Qlik-based, JS-rendered, no public API)
- **Workflow:** user manually exports CSV → drops into `backend-python/data/epa/rin_prices_2026.csv` (vintage-tagged filename so viewers know it's a snapshot) → next ingest picks it up. Rename to `_2027.csv` at year rollover and update `EpaRinFileClient.DEFAULT_PATH` in lockstep.
- **Client:** [`EpaRinFileClient`](backend-python/app/clients/epa_rin_file_client.py). Filters to canonical D6: `RIN Year == Transfer Year AND QAP Service Type == "Unverified"`. Source-tagged `epa_emts`, `LIVE_SOURCES` in `SeedDataStatusManager` so it doesn't trigger the seed banner.
- **Test coverage:** 4 tests in `test_epa_rin_file_client.py` (missing file, filter rules, date/price parsing, unparseable rows)
- **Seed provider does NOT emit RIN** — real data or nothing. Missing RIN falls back cleanly (rin_included=False on `MarginComposition`).

### Federal Register — RFS policy documents

- **Source:** `federalregister.gov/api/v1/documents.json` — free, un-authed, structured JSON
- **Client:** [`FederalRegisterClient`](backend-python/app/clients/federal_register_client.py). Filters by `agency=environmental-protection-agency` + `term="renewable fuel standard"`. Returns top 15 newest.
- **Storage:** new `rfs_documents` table keyed on `document_number` (EPA's own unique ID)
- **Cache:** 6-day freshness check in `_ingest_rfs_documents` — same pattern as CFTC COT. Runs at most once per week even on daily ingest.
- **Feeds:** Policy chip's context (top 3 docs) + the hyperlinked viz component

### Yahoo / EIA / CFTC — unchanged in mechanics

Same clients, same schedules. But note: the seed banner now flags RIN as a "live-capable" series that fell back to seed if no EPA CSV is present. Historically only Yahoo + EIA counted.

---

## 3. Ask Granite prompt engineering — the pattern that works

The single biggest lesson from this session: **never ask an LLM to do arithmetic or sorting on structured data. Do it server-side, hand it the answer, ask it to narrate.**

Three specific failure modes we hit:

**Failure 1 — LLM picks the wrong "biggest" item.** Granite was passed 7 margin components and asked to identify the largest. It picked D6 RIN (2nd largest) instead of ethanol revenue (largest). Fixed by pre-computing `ranked_contributions_abs` server-side with items sorted by absolute value; prompt now says *"cite `ranked_contributions_abs[0]` verbatim, do NOT pick a different line item."*

**Failure 2 — LLM invents a direction not supported by data.** Granite said "corn declined by $0.35" when corn actually rose $0.35. Fixed by pre-computing `ranked_price_moves_pct` with an explicit `direction` field (`up`/`down`/`flat`) and instructing Granite to cite it verbatim.

**Failure 3 — LLM flips signs when reasoning across multiple steps.** Granite reasoned *"lower WASDE → softer basis → compresses spread"* — the last step is backwards (softer basis widens the spread, not compresses). Fixed by pre-computing `crush_spread_implication_prose` server-side (`"softens the corn basis and WIDENS the physical crush spread"`) and instructing Granite to narrate that sentence verbatim rather than reason.

**Applied everywhere:** RIN chip has a `d6_rin_percentile_of_full_history_0_to_100` (integer, not 0-1 decimal, because Granite misread the decimal as "1.0 percentile"). Blending card has server-computed regime label. WASDE chip has pre-computed crush implication.

**Prompt language that works:** *"Do NOT invent a trend that contradicts it. Do NOT pick a different line item."* Numbered, imperative rules. LLM-in-the-loop features live and die by this rigor.

---

## 4. Blending Economics — the derived-signal card

**Formula:**

```
blender_advantage_$/gal  =  RBOB_$/gal  −  (ethanol_$/gal  −  D6_RIN_$/gal)
```

**Why the RIN is subtracted:** the refiner captures the RIN when they blend and can either use it toward their own RFS obligation or sell it separately. So their effective ethanol cost = physical price − RIN value.

**Interpretation:**
- Positive advantage → ethanol is a cheaper blendstock than gasoline → blenders push blend rates up toward E10/E15 ceiling
- Negative advantage → ethanol is more expensive than RBOB → blenders only blend to hit the RFS mandate floor

**Regime thresholds:** placeholder `±$0.30/gal` indifference band. Not derived from a historical distribution. Constant lives at `_BLENDING_INDIFFERENCE_BAND_USD` in `dashboard_manager.py`. **README documents this as a placeholder** so if a trader asks, you can point at the acknowledgement. A serious desk would replace with the 20th/80th percentiles of historical `blender_advantage` — same pattern as the warning rules.

**Known simplifications:**
- Uses front-month CBOT RBOB and CME EH ethanol — not physical rack prices at a specific terminal
- No freight to blending point (~$0.05–0.15/gal typical)
- No denaturant cost (~$0.05–0.10/gal)
- No terminal-specific basis
- National indicative signal, not any specific blender's P&L

**RBOB removed from `OVERVIEW_SERIES`** — it lives here now instead. Comment in the code explains why (not a crush model input; is a blendstock competitor).

---

## 5. Runtime / infrastructure notes

### Model bump — Granite 4-h-small on `/text/chat`

- `ibm/granite-3-8b-instruct` was withdrawn from watsonx.ai during this session
- Bumped to `ibm/granite-4-h-small` in `app_settings.py` + `watsonx_client.py`
- Migrated from deprecated `/ml/v1/text/generation` to current `/ml/v1/text/chat` endpoint
- Client signature: `generate(prompt: str, *, system: str | None = None, ...)` — pass system prompt separately, prompt becomes the user turn
- README's "Notice" section has a runnable snippet to check current Granite model IDs on your watsonx region if the briefing 404s again in the future

### File-drop pattern for RIN

- Only recurring manual step in the pipeline
- Weekly workflow documented in README under "Refreshing D6 RIN prices"
- If the file is missing entirely: RIN drops out of margin composition, RIN card shows dash, everything else works

### DuckDB migration idempotence

- Both `merged_daily.d6_rin_usd_per_gallon` and `rfs_documents` table use `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` patterns
- Safe to re-run on any existing DB — schema updates without data loss

### Ingest cadence table

| Source | Refresh | Trigger |
|---|---|---|
| Yahoo futures (ZC, EH, RB, NG) | Every ingest | On startup + admin trigger |
| EIA (weekly stocks + production) | Every ingest | On startup + admin trigger |
| CFTC COT | Weekly (6-day cache) | Skips if newest report < 6d old |
| EPA RIN CSV | Every ingest (reads local file) | Reads whatever's on disk |
| Federal Register | Weekly (6-day cache) | Skips if newest doc < 6d old |
| WASDE (JSON schedule) | Loaded at startup | From `config/wasde_schedule.json` |

---

## 6. Open items

### Not blocked on anything

1. **RIN share of margin sparkline / dedicated panel** — the "policy vs. market risk decomposition" idea from [`RIN_INSIGHT_HANDOFF.md`](RIN_INSIGHT_HANDOFF.md). Option A (small tile) is 1–2 hours; Option B (dedicated panel) is 4–6 hours. Would be genuinely differentiating for the pitch.
2. **Blending regime threshold tuning** — replace placeholder `±$0.30` with the 20th/80th percentile of the trailing-1Y `blender_advantage` distribution. Would take ~30 min. Not urgent, but improves defensibility.
3. **Two unused EPA CSVs** — `rin_transaction_volumes_2026.csv` and `rin_annual_sales_2026.csv` sit in `data/epa/` but aren't wired into anything. Transaction volume could feed a "RIN liquidity" signal. Not needed for current features.

### Would need user input

- **Video script updates** — several talking points from this session that could sharpen the pitch (RIN as biggest margin driver at cycle-highs; blender's advantage as trader decision surface; Policy chip as regulatory news feed). Only worth updating if user wants to re-record.
- **Regime thresholds** — see item 2 above; if user has intuition for the right band, use that instead of percentile-derived.

---

## 7. What NOT to do

- **Don't remove the pre-computed ranked/direction fields from Ask Granite contexts.** The prompt engineering pattern (do arithmetic server-side, narrate LLM-side) is the reason these chips are defensible. Adding "just let Granite figure it out" back into any prompt reintroduces the wrong-direction / wrong-item failure modes.
- **Don't add RBOB back to `OVERVIEW_SERIES`.** It lives in `blending_economics` for a reason. Comment in the code explains.
- **Don't remove the seed-RIN suppression.** Seed provider intentionally does not emit RIN. Real EPA data or nothing. The margin calculator handles missing RIN gracefully.
- **Don't build a live EPA dashboard scraper.** The Qlik dashboard is JS-rendered and changes periodically. File-drop is honest and stable. Federal Register is the live regulatory source; that's already automated.
- **Don't rotate the watsonx model without checking the API.** IBM removes models without long deprecation windows. Use the README snippet to list current Granite models on the user's region before hardcoding a replacement.
- **Don't touch the `_BLENDING_INDIFFERENCE_BAND_USD` without updating the README.** The README documents that it's a placeholder — if the value changes but the doc doesn't, the honesty story breaks.
- **Don't reuse `/text/generation` for new Granite calls.** Chat endpoint is required for Granite 4. See `watsonx_client.py` for the migration comment.

---

## 8. Testing

**57 unit tests.** Run:

```bash
cd backend-python && source .venv/bin/activate && python -m pytest tests/unit/ -q
```

Load-bearing tests to preserve when refactoring:

- `test_spread_matches_cme_crush_formula` — CME crush spread formula locked in
- `test_rin_revenue_lifts_margin_by_exactly_rin_price_times_yield` — RIN math verification
- `test_rin_missing_leaves_calculation_identical_to_pre_rin_math` — backward compat
- `test_margin_composition_sums_to_margin_per_bushel_with_rin` — decomposition invariant
- `test_backtester_does_not_pass_future_history_to_rule` — lookahead-bias canary
- `test_keeps_only_current_vintage_unverified_d6` — EPA CSV filter rule

---

## 9. Fast context for a fresh Claude session

If you drop this file (plus the README + `RIN_INSIGHT_HANDOFF.md`) into a fresh session and want to continue work:

- Stack: Python 3.13 + FastAPI + DuckDB backend, React 18 + Vite + uPlot frontend, IBM Granite 4-h-small on watsonx.ai via `/text/chat`
- The user is trader-literate and going into commodities. Prefer commodity-market vocabulary. Assume they understand crush margins, basis, contango. Explaining these = accidental condescension.
- Domain: corn ethanol dry-mill economics. Iowa State CARD model. All constants in `config/crush_model.json`.
- Hackathon is over. Current mode is refinement into "one defensible research output" (user's phrase). Not shipping to production users.
- Data is a mix of live feeds (Yahoo, EIA), file-drop (EPA RIN), scheduled scrapes (Federal Register), and static config (WASDE calendar).
- The user pushes back on things that look off. Take corrections seriously. They will notice sign-flips and layout awkwardness.

---

*End of handoff. If you make significant changes, append them to `§1 What's in the app now` above so the next context reload stays honest. Delete stale open items from `§6` as you complete them.*
