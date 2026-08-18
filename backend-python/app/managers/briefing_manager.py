"""Generates a natural-language signal briefing via IBM Granite / watsonx.ai."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from app.clients.cftc_cot_client import CftcCotClient
from app.clients.watsonx_client import WatsonxClient
from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.release_schedule_manager import ReleaseScheduleManager
from app.managers.series_merge_manager import SERIES_D6_RIN, SERIES_WASDE_CORN_ETHANOL
from app.managers.warning_backtester import RuleBacktestReport, WarningRuleBacktester
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import DuckDbRepository

_logger = logging.getLogger(__name__)


def _friendly_watsonx_error(exc: Exception) -> str:
    """
    Translate a raw watsonx.ai exception into a short, user-facing string.

    The client raises ``RuntimeError("watsonx.ai API error 429: {...raw JSON...}")``
    on API failures. Dumping that verbatim into the UI leaks a JSON blob into
    the briefing chip — not what a mentor viewing the dashboard should see.
    Full detail still goes to the server log via the caller's ``_logger.warning``.
    """
    raw = str(exc)
    if "429" in raw:
        if "consumption_limit_reached" in raw:
            return (
                "IBM Granite hit its shared free-tier concurrent request cap. "
                "Retry in ~30 seconds."
            )
        return "IBM Granite is briefly rate-limited. Retry in a moment."
    if "not configured" in raw:
        return "Granite briefing not configured on this deployment."
    if "401" in raw or "403" in raw:
        return "Granite auth failed — check watsonx credentials on the server."
    return "Granite briefing temporarily unavailable. Try again shortly."

_SYSTEM_INSTRUCTIONS = """You are a senior commodity analyst writing a concise daily briefing
for an ethanol crush trader. Write 3-5 sentences in plain, direct prose. Rules:
- Ground every claim in the numbers provided. Do not invent figures.
- Name the current signal label (rich / elevated / normal / soft / weak) in the first sentence.
- Mention the z-score and what percentile band it implies.
- If any warning rules fired, explain what the combination of signals means for the margin.
- If the backtest data shows meaningful hit rates, cite them briefly.
- Close with one forward-looking watch item (price leg, inventory build, or production pace).
- No bullet points. No headings. No em dashes. No markdown formatting.
- Maximum 5 sentences."""


def _build_user_prompt(context: dict) -> str:
    """Serialise the structured context into the user-turn content for Granite chat."""
    context_json = json.dumps(context, default=str, indent=2)
    return f"MARKET CONTEXT (JSON):\n{context_json}\n\nWrite the briefing now."


class BriefingManager:
    """
    Assembles structured context from the DB and calls Granite for prose.

    Casual: reads the live dashboard state and asks the LLM to narrate it.

    The LLM only sees structured facts — margins, z-scores, active warnings,
    backtest hit rates. Numbers are deterministic; prose is IBM Granite.
    The result is cached in the ``briefings`` DuckDB table keyed on the
    ingest-run timestamp so we don't burn tokens on unchanged state.
    """

    def __init__(
        self,
        repository: DuckDbRepository,
        watsonx_client: WatsonxClient,
        backtester: WarningRuleBacktester | None = None,
    ) -> None:
        self._repository = repository
        self._watsonx = watsonx_client
        self._backtester = backtester or WarningRuleBacktester(repository)

    @property
    def is_available(self) -> bool:
        """True when the watsonx client is configured."""
        return self._watsonx.is_configured

    def get_or_generate(self, ingest_cache_key: str | None = None) -> dict:
        """
        Return a cached briefing if current, otherwise generate a fresh one.

        ``ingest_cache_key`` is optional — when omitted, the manager derives it
        from the latest ingestion run so callers (like the API route) don't
        need to reach into repository internals.
        Returns ``{"as_of": ..., "text": ..., "cached": bool}``.
        """
        if not self.is_available:
            return {
                "as_of": None,
                "text": None,
                "cached": False,
                "unavailable_reason": "watsonx.ai not configured — set APP_WATSONX_API_KEY and APP_WATSONX_PROJECT_ID",
            }

        if ingest_cache_key is None:
            ingest_cache_key = self._current_ingest_cache_key()

        # Check DB cache first.
        cached = self._repository.fetch_latest_briefing()
        if cached and cached.get("cache_key") == ingest_cache_key and cached.get("text"):
            return {
                "as_of": cached["as_of"],
                "text": cached["text"],
                "cached": True,
            }

        # Build context and call Granite.
        context = self._build_context()
        try:
            text = self._watsonx.generate(
                _build_user_prompt(context),
                system=_SYSTEM_INSTRUCTIONS,
            )
        except Exception as exc:
            _logger.warning("watsonx.ai briefing generation failed: %s", exc)
            return {
                "as_of": context.get("as_of"),
                "text": None,
                "cached": False,
                "unavailable_reason": _friendly_watsonx_error(exc),
            }

        as_of = context.get("as_of")
        self._repository.upsert_briefing(
            as_of=as_of,
            text=text,
            cache_key=ingest_cache_key,
        )
        return {"as_of": as_of, "text": text, "cached": False}

    # ------------------------------------------------------------------
    # Context assembly — deterministic structured facts for the prompt
    # ------------------------------------------------------------------

    def _build_context(self) -> dict:
        """Pull latest margin, prices, warnings, and real backtest stats into one dict."""
        latest_margin = self._repository.fetch_latest_computed_margin()
        latest_merged = self._repository.fetch_latest_merged_daily()

        margin_ctx: dict = {}
        if latest_margin:
            margin_ctx = {
                "date": latest_margin.obs_date.isoformat(),
                "margin_per_bushel_usd": round(latest_margin.margin_per_bushel, 4),
                "margin_per_gallon_usd": round(latest_margin.margin_per_gallon, 4),
                "z_score": round(latest_margin.z_score, 3) if latest_margin.z_score is not None else None,
                "signal_label": latest_margin.signal_label,
                "corn_oil_included": latest_margin.corn_oil_included,
            }

        prices_ctx: dict = {}
        if latest_merged:
            prices_ctx = {
                "corn_usd_per_bushel": latest_merged.corn_usd_per_bushel,
                "ethanol_usd_per_gallon": latest_merged.ethanol_usd_per_gallon,
                "nat_gas_usd_per_mmbtu": latest_merged.nat_gas_usd_per_mmbtu,
                "ethanol_stocks_mmbbl": latest_merged.ethanol_stocks_mmbbl,
                "ethanol_production_mbpd": latest_merged.ethanol_production_mbpd,
                "rbob_usd_per_gallon": latest_merged.rbob_usd_per_gallon,
            }

        # Warnings from the latest margin date.
        warning_date = latest_margin.obs_date if latest_margin else None
        warnings_raw = (
            self._repository.fetch_warning_signals_for_date(warning_date) if warning_date else []
        )
        warnings_ctx = [
            {
                "signal_type": w["signal_type"],
                "severity": w["severity"],
                "message": w["message"],
            }
            for w in warnings_raw
        ]

        # Real backtest stats — run the full replay (fast: hits in-memory cache on
        # DashboardManager if it already ran, or builds a fresh one here).
        backtest_ctx = [
            _report_to_briefing_context(r) for r in self._backtester.run()
        ]

        return {
            "as_of": margin_ctx.get("date"),
            "crush_margin": margin_ctx,
            "input_prices": prices_ctx,
            "active_warnings": warnings_ctx,
            "rule_track_records": backtest_ctx,
        }

    def _current_ingest_cache_key(self) -> str | None:
        """
        Derive the cache key from the latest completed ingestion run.

        Encapsulated here so the API route doesn't reach into repository
        internals — the manager owns its own cache invalidation logic.
        """
        latest_ingest = self._repository.get_latest_ingestion_run()
        if not latest_ingest or not latest_ingest.get("finished_at"):
            return None
        return latest_ingest["finished_at"].isoformat()

    # ------------------------------------------------------------------
    # Preset question answering
    # ------------------------------------------------------------------

    PRESET_QUESTIONS: dict[str, str] = {
        "eia_interpretation": "Interpret the latest EIA weekly ethanol release",
        "wasde_interpretation": "Interpret the latest USDA WASDE corn-for-ethanol figure",
        "cot_interpretation": "Summarise the latest CFTC COT positioning for corn",
        "rin_market": "Summarise the current EPA D6 RIN market",
        "policy": "Summarise recent EPA / RFS regulatory activity",
        "margin_drivers": "What is driving the crush margin right now?",
    }

    def answer_preset_question(self, question_id: str) -> dict:
        """
        Answer one of the three preset questions using Granite.

        Each question gets its own context slice and system prompt so the
        model only sees data relevant to that question — no hallucination
        surface from unrelated series.

        Returns ``{"question_id", "question_label", "answer", "unavailable_reason"}``.
        The answer is always freshly generated (no cache) so the user gets
        up-to-date prose without a manual refresh.
        """
        if question_id not in self.PRESET_QUESTIONS:
            return {
                "question_id": question_id,
                "question_label": None,
                "answer": None,
                "unavailable_reason": f"Unknown question_id '{question_id}'. "
                    f"Valid: {list(self.PRESET_QUESTIONS)}",
            }

        if not self.is_available:
            return {
                "question_id": question_id,
                "question_label": self.PRESET_QUESTIONS[question_id],
                "answer": None,
                "unavailable_reason": "watsonx.ai not configured — set APP_WATSONX_API_KEY and APP_WATSONX_PROJECT_ID",
            }

        context_fn = {
            "eia_interpretation": self._eia_question_context,
            "wasde_interpretation": self._wasde_question_context,
            "cot_interpretation": self._cot_question_context,
            "rin_market": self._rin_question_context,
            "policy": self._policy_question_context,
            "margin_drivers": self._margin_drivers_context,
        }[question_id]
        system_prompt = _QUESTION_SYSTEM_PROMPTS[question_id]
        # A crash in the context builder shouldn't bubble up as an HTTP 500 —
        # log the full traceback for debugging and surface a friendly message
        # in the chip. Otherwise the UI just shows "Failed to fetch" and the
        # user has no signal about which data field went missing.
        try:
            context = context_fn()
        except Exception as exc:
            _logger.exception(
                "Preset question '%s' context build failed", question_id
            )
            return {
                "question_id": question_id,
                "question_label": self.PRESET_QUESTIONS[question_id],
                "answer": None,
                "unavailable_reason": (
                    f"Couldn't assemble the data slice for this chip "
                    f"({type(exc).__name__}). Check server logs for details."
                ),
            }

        context_json = json.dumps(context, default=str, indent=2)
        user_prompt = f"DATA (JSON):\n{context_json}\n\nAnswer the question now."

        try:
            answer = self._watsonx.generate(
                user_prompt,
                system=system_prompt,
                max_new_tokens=280,
            )
        except Exception as exc:
            _logger.warning("watsonx.ai preset question '%s' failed: %s", question_id, exc)
            return {
                "question_id": question_id,
                "question_label": self.PRESET_QUESTIONS[question_id],
                "answer": None,
                "unavailable_reason": _friendly_watsonx_error(exc),
            }

        return {
            "question_id": question_id,
            "question_label": self.PRESET_QUESTIONS[question_id],
            "answer": answer,
            "chart_data": context,   # raw numbers so the frontend can render sparklines
        }

    def _eia_question_context(self) -> dict:
        """Last 4 EIA weekly prints — stocks and production with WoW changes."""
        latest_margin = self._repository.fetch_latest_computed_margin()
        cutoff = (latest_margin.obs_date - timedelta(days=28)) if latest_margin else None

        from app.managers.series_merge_manager import SERIES_ETHANOL_STOCKS, SERIES_ETHANOL_PRODUCTION
        stocks_rows = self._repository.fetch_raw_observations_by_series(
            SERIES_ETHANOL_STOCKS, cutoff, None
        )
        production_rows = self._repository.fetch_raw_observations_by_series(
            SERIES_ETHANOL_PRODUCTION, cutoff, None
        )

        production_by_date = {r.obs_date: r.value for r in production_rows}
        releases: list[dict] = []
        prior_stocks: float | None = None
        prior_prod: float | None = None
        for row in stocks_rows[-5:]:  # last 5 = 4 WoW deltas
            stocks_mmbbl = round(row.value * 0.001, 3)
            prod = production_by_date.get(row.obs_date)
            releases.append({
                "date": row.obs_date.isoformat(),
                "stocks_mmbbl": stocks_mmbbl,
                "stocks_wow_pct": round((stocks_mmbbl - prior_stocks) / prior_stocks, 4)
                    if prior_stocks else None,
                "production_mbpd": prod,
                "production_wow_pct": round((prod - prior_prod) / prior_prod, 4)
                    if (prod and prior_prod) else None,
            })
            prior_stocks = stocks_mmbbl
            if prod is not None:
                prior_prod = prod

        latest_margin_ctx = {}
        if latest_margin:
            latest_margin_ctx = {
                "margin_per_bushel_usd": round(latest_margin.margin_per_bushel, 4),
                "signal_label": latest_margin.signal_label,
            }
        return {
            "eia_weekly_releases": releases[-4:],  # drop the anchor row used for WoW
            "current_margin": latest_margin_ctx,
        }

    def _cot_question_context(self) -> dict:
        """Latest COT print plus 4-week history of managed-money net."""
        latest = self._repository.fetch_latest_cot_report(CftcCotClient.CBOT_CORN_CODE)
        if latest is None:
            return {"cot_data": None}

        cutoff = latest["report_date"] - timedelta(weeks=4)
        history = self._repository.fetch_cot_reports(
            CftcCotClient.CBOT_CORN_CODE, start_date=cutoff
        )
        full_history = self._repository.fetch_cot_reports(CftcCotClient.CBOT_CORN_CODE)

        # 5Y percentile of managed-money net.
        nets_5y = sorted(
            r["managed_money_long"] - r["managed_money_short"] for r in full_history
        )
        latest_net = latest["managed_money_long"] - latest["managed_money_short"]
        pct_rank = round(
            sum(1 for n in nets_5y if n <= latest_net) / len(nets_5y), 3
        ) if nets_5y else None

        prior = self._repository.fetch_prior_cot_report(
            CftcCotClient.CBOT_CORN_CODE, latest["report_date"]
        )
        prior_net = (prior["managed_money_long"] - prior["managed_money_short"]) if prior else None

        return {
            "latest_cot": {
                "report_date": latest["report_date"].isoformat(),
                "managed_money_net_contracts": latest_net,
                "managed_money_net_wow": (latest_net - prior_net) if prior_net is not None else None,
                "producer_net_contracts": latest["producer_long"] - latest["producer_short"],
                "open_interest": latest["open_interest"],
                "mm_net_percentile_5y": pct_rank,
            },
            "recent_mm_net_4w": [
                {
                    "date": r["report_date"].isoformat(),
                    "mm_net": r["managed_money_long"] - r["managed_money_short"],
                }
                for r in history
            ],
        }

    def _policy_question_context(self) -> dict:
        """
        Recent EPA RFS regulatory activity + current market pricing lens.

        The Federal Register ingester keeps ``rfs_documents`` fresh weekly.
        We surface the latest 3 documents alongside where D6 RIN is trading —
        gives Granite both the qualitative catalyst and the market's response.
        """
        docs = self._repository.fetch_latest_rfs_documents(limit=3)
        latest_docs: list[dict] = []
        for doc in docs:
            latest_docs.append({
                "publication_date": doc["publication_date"].isoformat(),
                "type": doc.get("doc_type") or "Document",
                "title": doc["title"],
                # Truncate abstract so Granite doesn't drown in regulatory prose.
                "abstract": (doc.get("abstract") or "")[:400],
                "url": doc["html_url"],
            })

        days_since_latest = None
        if docs:
            days_since_latest = (date.today() - docs[0]["publication_date"]).days

        # Current market lens for the closing sentence.
        rin_rows = self._repository.fetch_raw_observations_by_series(SERIES_D6_RIN)
        rin_context: dict = {}
        if rin_rows:
            latest_rin = rin_rows[-1]
            all_values = sorted(row.value for row in rin_rows)
            pct = round(
                sum(1 for v in all_values if v <= latest_rin.value) / len(all_values), 3
            )
            rin_context = {
                "d6_rin_price_usd_per_gallon": round(latest_rin.value, 4),
                "d6_rin_percentile_of_full_history_0_to_100": round(pct * 100),
                "d6_rin_full_history_median_usd_per_gallon": round(
                    all_values[len(all_values) // 2], 4
                ),
            }

        return {
            "recent_rfs_documents": latest_docs,
            "days_since_latest_document": days_since_latest,
            "current_market_lens": rin_context,
        }

    def _rin_question_context(self) -> dict:
        """
        D6 RIN market context: latest print, WoW, 5Y percentile, share of margin.

        Numbers are pre-computed so Granite narrates instead of ranking or
        computing arithmetic across a long series.
        """
        rin_rows = self._repository.fetch_raw_observations_by_series(SERIES_D6_RIN)
        if not rin_rows:
            return {"d6_rin": None}

        latest = rin_rows[-1]
        prior = rin_rows[-2] if len(rin_rows) >= 2 else None
        wow_abs = (latest.value - prior.value) if prior else None
        wow_pct = (wow_abs / prior.value) if (wow_abs is not None and prior.value) else None

        all_values = sorted(row.value for row in rin_rows)
        pct_rank = round(
            sum(1 for v in all_values if v <= latest.value) / len(all_values), 3
        )

        four_week = rin_rows[-4:] if len(rin_rows) >= 4 else rin_rows
        trend_4w = [
            {"date": row.obs_date.isoformat(), "price_usd_per_gallon": round(row.value, 4)}
            for row in four_week
        ]

        # D6 regulatory value expressed as a ratio to the plant's physical
        # operating margin — a compliance-market-vs-physical-margin scale
        # comparison, NOT a claim about producer capture. Ratio can exceed
        # 100% (correctly) when regulatory value is larger than plant P&L.
        rin_share_of_margin_pct: float | None = None
        latest_merged = self._repository.fetch_latest_merged_daily()
        latest_margin = self._repository.fetch_latest_computed_margin()
        if latest_merged and latest_margin and latest_margin.margin_per_bushel > 0:
            calculator = CrushMarginCalculator(CrushModelConfig.default())
            comp = calculator.decompose(latest_merged)
            if comp is not None and comp.rin_included:
                rin_share_of_margin_pct = round(
                    comp.d6_rin_value / latest_margin.margin_per_bushel * 100, 1
                )

        return {
            "d6_rin": {
                "latest_price_usd_per_gallon": round(latest.value, 4),
                "latest_report_date": latest.obs_date.isoformat(),
                "wow_abs_change": round(wow_abs, 4) if wow_abs is not None else None,
                "wow_pct_change": round(wow_pct, 4) if wow_pct is not None else None,
                "percentile_full_history": pct_rank,
                "history_min": round(all_values[0], 4),
                "history_max": round(all_values[-1], 4),
                "history_median": round(all_values[len(all_values) // 2], 4),
                "history_years": rin_rows[-1].obs_date.year - rin_rows[0].obs_date.year,
                "recent_4w_prints": trend_4w,
            },
            "rin_share_of_current_margin_pct": rin_share_of_margin_pct,
        }

    def _wasde_question_context(self) -> dict:
        """
        USDA WASDE corn-for-ethanol context: latest reading, trend, next release.

        Ships pre-computed deltas + a 6-report trend direction so Granite doesn't
        have to compute revisions in its head.
        """
        wasde_rows = self._repository.fetch_raw_observations_by_series(
            SERIES_WASDE_CORN_ETHANOL
        )
        if not wasde_rows:
            return {"wasde": None}

        latest = wasde_rows[-1]
        prior = wasde_rows[-2] if len(wasde_rows) >= 2 else None
        delta_vs_prior = (latest.value - prior.value) if prior else None

        recent_6 = wasde_rows[-6:] if len(wasde_rows) >= 6 else wasde_rows
        trend = [
            {"report_date": row.obs_date.isoformat(), "corn_for_ethanol_mbu": round(row.value, 0)}
            for row in recent_6
        ]
        # Direction of last 6 reports: are analysts revising up or down?
        revision_direction = "flat"
        if len(recent_6) >= 2:
            net = recent_6[-1].value - recent_6[0].value
            revision_direction = "up" if net > 25 else ("down" if net < -25 else "flat")

        next_release = ReleaseScheduleManager().next_wasde_release()

        # Pre-compute the crush-spread implication so Granite doesn't have to
        # chain "revision → basis direction → spread direction" itself — a
        # multi-step signed reasoning task LLMs consistently invert.
        # Rule: higher WASDE ethanol demand → firmer corn basis → COMPRESSES
        # the simple ethanol/corn spread. Lower → softer basis → WIDENS.
        if delta_vs_prior is None or abs(delta_vs_prior) < 5:
            crush_implication = "neutral"
            crush_implication_prose = (
                "The revision is small and unlikely to move the simple ethanol/corn spread meaningfully "
                "over the next 30 days."
            )
        elif delta_vs_prior > 0:
            crush_implication = "compresses"
            crush_implication_prose = (
                "This upward revision implies firmer nearby corn demand, which typically firms "
                "the corn basis and COMPRESSES the simple ethanol/corn spread over the next 30 days."
            )
        else:
            crush_implication = "widens"
            crush_implication_prose = (
                "This downward revision implies softer nearby corn demand, which typically softens "
                "the corn basis and WIDENS the simple ethanol/corn spread over the next 30 days."
            )

        return {
            "wasde": {
                "latest_report_date": latest.obs_date.isoformat(),
                "corn_for_ethanol_mbu": round(latest.value, 0),
                "delta_vs_prior_mbu": round(delta_vs_prior, 0) if delta_vs_prior is not None else None,
                "revision_direction_last_6_reports": revision_direction,
                "recent_6_reports": trend,
                "next_release_date": next_release.released_at_et.date().isoformat(),
                "next_release_is_approximate": next_release.is_approximate,
                "crush_spread_implication": crush_implication,
                "crush_spread_implication_prose": crush_implication_prose,
            },
        }

    def _margin_drivers_context(self) -> dict:
        """
        Latest prices, per-lever contribution, and 4-week trend for margin drivers.

        Ships pre-ranked lists so Granite doesn't have to sort or arithmetic
        across seven line items in its head — a class of task LLMs get wrong.
        `ranked_contributions_abs` and `ranked_price_moves_pct` are both
        largest-first; Granite is instructed to narrate `[0]` verbatim.
        """
        latest_margin = self._repository.fetch_latest_computed_margin()

        cutoff = (latest_margin.obs_date - timedelta(days=28)) if latest_margin else None
        recent = self._repository.fetch_merged_daily(start_date=cutoff)

        # ---- Pre-ranked 4-week price moves (largest % change first) ----
        price_moves: list[dict] = []
        if len(recent) >= 2:
            first = recent[0]
            last = recent[-1]
            price_fields = [
                ("corn", "corn_usd_per_bushel", "$/bu"),
                ("ethanol", "ethanol_usd_per_gallon", "$/gal"),
                ("ddgs", "ddgs_usd_per_short_ton", "$/short ton"),
                ("corn_oil", "corn_oil_usd_per_pound", "$/lb"),
                ("nat_gas", "nat_gas_usd_per_mmbtu", "$/MMBtu"),
                ("rbob", "rbob_usd_per_gallon", "$/gal"),
                ("d6_rin", "d6_rin_usd_per_gallon", "$/gal"),
            ]
            for label, field, unit in price_fields:
                v0 = getattr(first, field, None)
                v1 = getattr(last, field, None)
                if v0 is None or v1 is None or v0 == 0:
                    continue
                price_moves.append({
                    "leg": label,
                    "unit": unit,
                    "value_4w_ago": round(v0, 4),
                    "value_now": round(v1, 4),
                    "abs_change": round(v1 - v0, 4),
                    "pct_change": round((v1 - v0) / abs(v0), 4),
                    "direction": "up" if v1 > v0 else ("down" if v1 < v0 else "flat"),
                })
            price_moves.sort(key=lambda m: abs(m["pct_change"]), reverse=True)

        # ---- Pre-ranked current-margin contributions (largest |$/bu| first) ----
        composition_by_label: dict = {}
        ranked_contributions: list[dict] = []
        if recent:
            latest_row = recent[-1]
            calculator = CrushMarginCalculator(CrushModelConfig.default())
            comp = calculator.decompose(latest_row)
            if comp is not None:
                # PHYSICAL drivers only — D6 RIN is a compliance-market value,
                # NOT a producer revenue line, so it's tracked separately below
                # and excluded from the "biggest physical driver" ranking Granite
                # cites in its closing sentence.
                candidates = [
                    ("Ethanol revenue",  comp.ethanol_revenue,  "revenue"),
                    ("DDGS revenue",     comp.ddgs_revenue,     "revenue"),
                ]
                if comp.corn_oil_included:
                    candidates.append(("Corn oil revenue", comp.corn_oil_revenue, "revenue"))
                candidates += [
                    ("Corn cost",       comp.corn_cost,     "cost"),
                    ("Natural gas cost", comp.nat_gas_cost, "cost"),
                    ("Misc opex",       comp.misc_opex_cost, "cost"),
                ]
                composition_by_label = {label: round(v, 4) for label, v, _ in candidates}
                ranked_contributions = sorted(
                    [
                        {"lever": label, "kind": kind, "value_per_bushel": round(v, 4)}
                        for label, v, kind in candidates
                    ],
                    key=lambda c: abs(c["value_per_bushel"]),
                    reverse=True,
                )
                # Expose the D6 RIN value on its own so prompts can reference
                # the regulatory-value scale without adding it to the physical
                # driver ranking (which would misframe it as producer revenue).
                if comp.rin_included:
                    composition_by_label["D6 RIN Value (regulatory)"] = round(comp.d6_rin_value, 4)

        current_margin = {}
        if latest_margin:
            current_margin = {
                "margin_per_bushel_usd": round(latest_margin.margin_per_bushel, 4),
                "margin_per_gallon_usd": round(latest_margin.margin_per_gallon, 4),
                "z_score": round(latest_margin.z_score, 3) if latest_margin.z_score is not None else None,
                "signal_label": latest_margin.signal_label,
            }

        # Raw 4-week trend rows for the frontend MarginDriverBars viz —
        # kept alongside the ranked lists so the chart survives and Granite
        # can also spot patterns not captured by the ranked summary.
        price_trend: list[dict] = [
            {
                "date": row.obs_date.isoformat(),
                "corn_usd_per_bushel": row.corn_usd_per_bushel,
                "ethanol_usd_per_gallon": row.ethanol_usd_per_gallon,
                "nat_gas_usd_per_mmbtu": row.nat_gas_usd_per_mmbtu,
            }
            for row in recent[-5:]
        ]

        return {
            "current_margin": current_margin,
            "ranked_contributions_abs": ranked_contributions,
            "margin_composition_by_label": composition_by_label,
            "ranked_price_moves_pct": price_moves,
            "recent_price_trend": price_trend,
        }


# ------------------------------------------------------------------
# Preset question system prompts — one per question_id
# ------------------------------------------------------------------

_QUESTION_SYSTEM_PROMPTS: dict[str, str] = {
    "eia_interpretation": (
        "You are a commodity analyst interpreting the latest EIA Weekly Petroleum Status Report "
        "for an ethanol crush trader. Write 3-4 sentences in plain prose. Rules: "
        "cite the actual stock level and WoW change in the first sentence; "
        "state whether production is trending up or down and by how much; "
        "explain what the combination of stocks and production means for the near-term "
        "ethanol price and crush margin; "
        "close with one actionable watch item. "
        "No bullet points. No markdown. No invented numbers. Maximum 4 sentences."
    ),
    "cot_interpretation": (
        "You are a commodity analyst interpreting the latest CFTC Commitments of Traders report "
        "for CBOT Corn futures. Write 3-4 sentences in plain prose. Rules: "
        "open with the managed-money net position and its 5-year percentile rank; "
        "describe the WoW change and what direction that implies for speculative pressure; "
        "compare managed-money to commercial (producer) positioning to identify any imbalance; "
        "close with what a shift in fund positioning would mean for corn prices and therefore "
        "the ethanol crush margin. "
        "No bullet points. No markdown. No invented numbers. Maximum 4 sentences."
    ),
    "rin_market": (
        "You are a commodity analyst summarising the EPA D6 corn ethanol RIN market for a trader. "
        "Write 3-4 sentences in plain prose. Follow these rules exactly:\n"
        "1. Open with the current D6 RIN price and its `percentile_full_history` — cite both verbatim.\n"
        "2. State the WoW change from `wow_pct_change` (direction and magnitude).\n"
        "3. Cite `rin_share_of_current_margin_pct` as the scale of the D6 REGULATORY VALUE relative "
        "to the plant's physical operating margin. Frame it as a COMPLIANCE-VALUE comparison, NOT as "
        "producer revenue capture. If above 40%, note that the compliance-market value attached to the "
        "ethanol gallon is currently large relative to physical plant P&L, making the sector's aggregate "
        "economics sensitive to EPA policy (SRE grants, RVO decisions, Set Rule).\n"
        "4. DIRECTIONAL RULE FOR THE CLOSING SENTENCE: The D6 RIN price sets the market value of the "
        "compliance credit attached to each gallon of ethanol produced. It is NOT assumed to be "
        "dollar-for-dollar producer revenue — producer capture depends on pass-through economics between "
        "producers and obligated parties (refiners/importers), which this dashboard does not model. "
        "Discuss RIN moves in terms of SECTOR-LEVEL compliance value and POLICY signal, not direct "
        "plant P&L. Avoid the words 'revenue', 'plant captures', 'producer pockets', or 'margin' when "
        "referring to the RIN price itself.\n"
        "No bullet points, no markdown, no invented numbers. Maximum 4 sentences."
    ),
    "wasde_interpretation": (
        "You are a commodity analyst interpreting the latest USDA WASDE corn-for-ethanol figure. "
        "Write 3-4 sentences in plain prose. Follow these rules exactly:\n"
        "1. Cite `corn_for_ethanol_mbu` and `delta_vs_prior_mbu` verbatim. State direction and magnitude.\n"
        "2. Cite `revision_direction_last_6_reports` verbatim — 'up', 'down', or 'flat'. Do NOT invent a "
        "different trend.\n"
        "3. Cite `next_release_date`.\n"
        "4. For the CRUSH SPREAD IMPLICATION, use `crush_spread_implication_prose` verbatim or paraphrase "
        "it faithfully. Do NOT invent a different directional conclusion. The server has already computed "
        "the correct direction — you narrate, do not reason.\n"
        "No bullet points, no markdown, no invented numbers. Maximum 4 sentences."
    ),
    "policy": (
        "You are a commodity analyst summarising recent EPA / RFS regulatory activity for a "
        "biofuels trader. Write 3-4 sentences in plain prose. Follow these rules exactly:\n"
        "1. Open with the SINGLE most recent document from `recent_rfs_documents[0]` — cite "
        "the `type`, a short paraphrase of the `title`, and the `publication_date`. Do NOT cite "
        "a different item as the most recent.\n"
        "2. In one sentence, characterise what this action likely means for D6 RIN demand — "
        "SRE decisions typically REDUCE demand (bearish), Set Rules / RVO finalisations that "
        "raise volume requirements typically INCREASE demand (bullish), information collection "
        "renewals are neutral.\n"
        "3. Cite `current_market_lens.d6_rin_price_usd_per_gallon` in dollars per gallon and "
        "`d6_rin_percentile_of_full_history_0_to_100` as an integer percentile (e.g. '87th percentile'). "
        "This tells the reader where the market has priced things right now.\n"
        "4. If there is a second recent action in `recent_rfs_documents[1]`, mention it briefly "
        "as ongoing context. Otherwise skip.\n"
        "No bullet points, no markdown, no invented numbers, no fabricated URLs. Maximum 4 sentences."
    ),
    "margin_drivers": (
        "You are a commodity analyst explaining what is driving the ethanol crush margin. "
        "Write 3-4 sentences in plain prose. Follow these rules exactly:\n"
        "1. The biggest current contributor to the margin is `ranked_contributions_abs[0]` — "
        "cite its lever name and $/bu value verbatim. Do NOT pick a different line item.\n"
        "2. The biggest 4-week price move is `ranked_price_moves_pct[0]` — cite its leg, "
        "the direction (up/down), and the pct_change. Do NOT invent a different mover.\n"
        "3. Costs (corn, nat gas, misc opex) are stored as negative numbers. A price DROP "
        "in a cost is FAVORABLE for the margin; a price RISE in a cost is UNFAVORABLE.\n"
        "4. State whether the margin is wide or narrow relative to history using `current_margin.signal_label`.\n"
        "5. Name the single biggest near-term risk — pick the lever most likely to move against "
        "the margin, and say which direction hurts.\n"
        "No bullet points, no markdown, no invented numbers. Maximum 4 sentences."
    ),
}


def _report_to_briefing_context(report: RuleBacktestReport) -> dict:
    """
    Extract the prompt-relevant slice of a backtest report.

    Keeps the payload small: one row per rule, 30d horizon only,
    no raw firing dates (irrelevant to the prose model).
    """
    return {
        "signal_type": report.signal_type,
        "expected_direction": report.expected_direction,
        "fire_count": report.fire_count,
        "hit_rate_30d": report.hit_rate_by_horizon.get(30),
        "median_move_30d_usd": report.median_move_by_horizon.get(30),
        "p25_move_30d_usd": report.p25_move_by_horizon.get(30),
        "p75_move_30d_usd": report.p75_move_by_horizon.get(30),
    }
