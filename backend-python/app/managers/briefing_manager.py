"""Generates a natural-language signal briefing via IBM Granite / watsonx.ai."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from app.clients.cftc_cot_client import CftcCotClient
from app.clients.watsonx_client import WatsonxClient
from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.managers.warning_backtester import RuleBacktestReport, WarningRuleBacktester
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import DuckDbRepository

_logger = logging.getLogger(__name__)

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
                "unavailable_reason": str(exc),
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
        "cot_interpretation": "Summarise the latest CFTC COT positioning for corn",
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
            "cot_interpretation": self._cot_question_context,
            "margin_drivers": self._margin_drivers_context,
        }[question_id]
        system_prompt = _QUESTION_SYSTEM_PROMPTS[question_id]
        context = context_fn()

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
                "unavailable_reason": str(exc),
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
                candidates = [
                    ("Ethanol revenue",  comp.ethanol_revenue,  "revenue"),
                    ("DDGS revenue",     comp.ddgs_revenue,     "revenue"),
                ]
                if comp.corn_oil_included:
                    candidates.append(("Corn oil revenue", comp.corn_oil_revenue, "revenue"))
                if comp.rin_included:
                    candidates.append(("D6 RIN revenue", comp.rin_revenue, "revenue"))
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

        current_margin = {}
        if latest_margin:
            current_margin = {
                "margin_per_bushel_usd": round(latest_margin.margin_per_bushel, 4),
                "margin_per_gallon_usd": round(latest_margin.margin_per_gallon, 4),
                "z_score": round(latest_margin.z_score, 3) if latest_margin.z_score is not None else None,
                "signal_label": latest_margin.signal_label,
            }

        return {
            "current_margin": current_margin,
            "ranked_contributions_abs": ranked_contributions,
            "margin_composition_by_label": composition_by_label,
            "ranked_price_moves_pct": price_moves,
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
