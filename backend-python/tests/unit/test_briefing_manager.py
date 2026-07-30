"""Unit tests for BriefingManager — three response shapes and backtest wiring."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.clients.watsonx_client import WatsonxClient
from app.managers.briefing_manager import BriefingManager, _report_to_briefing_context
from app.managers.warning_backtester import RuleBacktestReport, WarningRuleBacktester


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unconfigured_client() -> WatsonxClient:
    """WatsonxClient with no credentials."""
    return WatsonxClient(api_key="", project_id="")


def _configured_client(generated_text: str = "Margin is normal.") -> WatsonxClient:
    """WatsonxClient stub that returns canned text without hitting the network."""
    client = WatsonxClient(api_key="test-key", project_id="test-project")
    client.generate = MagicMock(return_value=generated_text)
    return client


def _stub_repository(
    *,
    has_margin: bool = True,
    briefing_row: dict | None = None,
) -> MagicMock:
    """Minimal DuckDbRepository stub."""
    repo = MagicMock()

    if has_margin:
        margin = MagicMock()
        margin.obs_date = date(2025, 6, 1)
        margin.margin_per_bushel = 3.50
        margin.margin_per_gallon = 3.50 / 2.8
        margin.z_score = 1.62
        margin.signal_label = "rich"
        margin.corn_oil_included = True
        repo.fetch_latest_computed_margin.return_value = margin
    else:
        repo.fetch_latest_computed_margin.return_value = None

    merged = MagicMock()
    merged.corn_usd_per_bushel = 4.52
    merged.ethanol_usd_per_gallon = 1.85
    merged.nat_gas_usd_per_mmbtu = 2.30
    merged.ethanol_stocks_mmbbl = 22.4
    merged.ethanol_production_mbpd = 1050.0
    merged.rbob_usd_per_gallon = 2.05
    repo.fetch_latest_merged_daily.return_value = merged

    repo.fetch_warning_signals_for_date.return_value = []
    repo.fetch_latest_briefing.return_value = briefing_row
    repo.upsert_briefing.return_value = None
    return repo


def _stub_backtester(reports: list[RuleBacktestReport] | None = None) -> WarningRuleBacktester:
    """WarningRuleBacktester stub that returns pre-built reports."""
    bt = MagicMock(spec=WarningRuleBacktester)
    bt.run.return_value = reports or []
    return bt


def _sample_report(signal_type: str = "bullish_margin_setup") -> RuleBacktestReport:
    return RuleBacktestReport(
        signal_type=signal_type,
        expected_direction="up",
        horizons_days=(7, 30, 60),
        fire_count=12,
        hit_rate_by_horizon={7: 0.58, 30: 0.67, 60: 0.50},
        median_move_by_horizon={7: 0.18, 30: 0.42, 60: 0.31},
        p25_move_by_horizon={7: -0.05, 30: 0.10, 60: 0.02},
        p75_move_by_horizon={7: 0.30, 30: 0.75, 60: 0.60},
    )


# ---------------------------------------------------------------------------
# Shape 1: watsonx not configured
# ---------------------------------------------------------------------------

def test_returns_unavailable_when_not_configured():
    mgr = BriefingManager(
        repository=_stub_repository(),
        watsonx_client=_unconfigured_client(),
        backtester=_stub_backtester(),
    )
    result = mgr.get_or_generate(ingest_cache_key="any")
    assert result["text"] is None
    assert "unavailable_reason" in result
    assert result["cached"] is False


# ---------------------------------------------------------------------------
# Shape 2: cache hit
# ---------------------------------------------------------------------------

def test_returns_cached_briefing_when_key_matches():
    cached_row = {
        "as_of": "2025-06-01",
        "text": "Cached briefing text.",
        "cache_key": "key-abc",
        "generated_at": "2025-06-01T12:00:00+00:00",
    }
    repo = _stub_repository(briefing_row=cached_row)
    mgr = BriefingManager(
        repository=repo,
        watsonx_client=_configured_client(),
        backtester=_stub_backtester(),
    )
    result = mgr.get_or_generate(ingest_cache_key="key-abc")
    assert result["cached"] is True
    assert result["text"] == "Cached briefing text."
    # Granite must not be called on a cache hit.
    mgr._watsonx.generate.assert_not_called()


def test_cache_miss_when_key_differs():
    cached_row = {
        "as_of": "2025-05-31",
        "text": "Old briefing.",
        "cache_key": "key-old",
        "generated_at": "2025-05-31T12:00:00+00:00",
    }
    repo = _stub_repository(briefing_row=cached_row)
    mgr = BriefingManager(
        repository=repo,
        watsonx_client=_configured_client("Fresh prose."),
        backtester=_stub_backtester(),
    )
    result = mgr.get_or_generate(ingest_cache_key="key-new")
    assert result["cached"] is False
    assert result["text"] == "Fresh prose."


# ---------------------------------------------------------------------------
# Shape 3: fresh generation
# ---------------------------------------------------------------------------

def test_fresh_generation_calls_granite_and_persists():
    repo = _stub_repository(briefing_row=None)
    client = _configured_client("Fresh briefing text.")
    mgr = BriefingManager(
        repository=repo,
        watsonx_client=client,
        backtester=_stub_backtester(),
    )
    result = mgr.get_or_generate(ingest_cache_key="key-xyz")
    assert result["text"] == "Fresh briefing text."
    assert result["cached"] is False
    client.generate.assert_called_once()
    repo.upsert_briefing.assert_called_once_with(
        as_of="2025-06-01",
        text="Fresh briefing text.",
        cache_key="key-xyz",
    )


def test_generation_failure_returns_unavailable_without_raising():
    repo = _stub_repository(briefing_row=None)
    client = _configured_client()
    client.generate = MagicMock(side_effect=RuntimeError("API timeout"))
    mgr = BriefingManager(
        repository=repo,
        watsonx_client=client,
        backtester=_stub_backtester(),
    )
    result = mgr.get_or_generate(ingest_cache_key="key-xyz")
    assert result["text"] is None
    assert "API timeout" in result["unavailable_reason"]
    repo.upsert_briefing.assert_not_called()


# ---------------------------------------------------------------------------
# Backtest wiring
# ---------------------------------------------------------------------------

def test_backtest_reports_included_in_context():
    """rule_track_records must be populated from the real backtester, not empty."""
    repo = _stub_repository(briefing_row=None)
    report = _sample_report("bullish_margin_setup")
    bt = _stub_backtester([report])
    captured_prompt: list[str] = []

    client = _configured_client()
    client.generate = MagicMock(
        side_effect=lambda prompt: captured_prompt.append(prompt) or "ok"
    )

    mgr = BriefingManager(repository=repo, watsonx_client=client, backtester=bt)
    mgr.get_or_generate(ingest_cache_key="k")

    assert captured_prompt, "generate() was never called"
    prompt = captured_prompt[0]
    assert "bullish_margin_setup" in prompt
    assert "0.67" in prompt   # hit_rate_30d from sample report
    assert "0.42" in prompt   # median_move_30d_usd from sample report


def test_backtest_context_shape():
    """_report_to_briefing_context extracts exactly the expected keys."""
    report = _sample_report("stocks_building_rich_margin")
    ctx = _report_to_briefing_context(report)
    assert ctx["signal_type"] == "stocks_building_rich_margin"
    assert ctx["expected_direction"] == "up"
    assert ctx["fire_count"] == 12
    assert ctx["hit_rate_30d"] == pytest.approx(0.67)
    assert ctx["median_move_30d_usd"] == pytest.approx(0.42)
    assert ctx["p25_move_30d_usd"] == pytest.approx(0.10)
    assert ctx["p75_move_30d_usd"] == pytest.approx(0.75)
    # Raw firings must NOT be in the context (prompt-size discipline).
    assert "firings" not in ctx
