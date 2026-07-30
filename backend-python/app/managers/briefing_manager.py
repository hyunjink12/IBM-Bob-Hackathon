"""Generates a natural-language signal briefing via IBM Granite / watsonx.ai."""

from __future__ import annotations

import json
import logging
from datetime import date

from app.clients.watsonx_client import WatsonxClient
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


def _build_prompt(context: dict) -> str:
    """Serialise the structured context into a single prompt string for Granite."""
    context_json = json.dumps(context, default=str, indent=2)
    return f"""{_SYSTEM_INSTRUCTIONS}

MARKET CONTEXT (JSON):
{context_json}

BRIEFING:"""


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

        ``ingest_cache_key`` should be the ISO timestamp of the latest ingestion
        run so the cache invalidates automatically after new data lands.
        Returns ``{"as_of": ..., "text": ..., "cached": bool}``.
        """
        if not self.is_available:
            return {
                "as_of": None,
                "text": None,
                "cached": False,
                "unavailable_reason": "watsonx.ai not configured — set APP_WATSONX_API_KEY and APP_WATSONX_PROJECT_ID",
            }

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
            text = self._watsonx.generate(_build_prompt(context))
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
