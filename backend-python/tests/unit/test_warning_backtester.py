"""Unit tests for the warning rule backtester."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.managers.warning_backtester import WarningRuleBacktester
from app.managers.warning_rules.base_rule import WarningRule, WarningSignal
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


class _AlwaysFireRule(WarningRule):
    """Test double: fires every day so we can inspect cooldown + slicing math."""

    @property
    def signal_type(self) -> str:
        return "always_fire"

    def evaluate(self, latest_row, margin_row, history, margin_history):
        return WarningSignal(
            signal_type=self.signal_type,
            severity="medium",
            message="",
            suggested_trade="",
            metadata={},
        )


class _LookaheadCanaryRule(WarningRule):
    """Test double: fires only if history contains any date AFTER the current row."""

    @property
    def signal_type(self) -> str:
        return "lookahead_canary"

    def evaluate(self, latest_row, margin_row, history, margin_history):
        future_leak = any(row.obs_date > latest_row.obs_date for row in history)
        if not future_leak:
            return None
        return WarningSignal(
            signal_type=self.signal_type,
            severity="high",
            message="",
            suggested_trade="",
            metadata={},
        )


class _FakeRepo:
    """Minimal repo stub — the backtester only calls three methods."""

    def __init__(
        self,
        merged: list[MergedDailyRow],
        margins: list[ComputedMarginRow],
    ) -> None:
        self._merged = merged
        self._margins = margins

    def fetch_merged_daily(self, *args, **kwargs) -> list[MergedDailyRow]:
        return self._merged

    def fetch_computed_margins(self, *args, **kwargs) -> list[ComputedMarginRow]:
        return self._margins


def _build_history(days: int, start: date = date(2020, 1, 1)) -> tuple[
    list[MergedDailyRow], list[ComputedMarginRow]
]:
    merged = []
    margins = []
    for i in range(days):
        obs = start + timedelta(days=i)
        merged.append(
            MergedDailyRow(
                obs_date=obs,
                corn_usd_per_bushel=4.5,
                ethanol_usd_per_gallon=1.8,
                ddgs_usd_per_short_ton=160.0,
                rbob_usd_per_gallon=2.2,
                nat_gas_usd_per_mmbtu=2.5,
                ethanol_stocks_mmbbl=22.0,
                ethanol_production_mbpd=1000.0,
                corn_oil_usd_per_pound=0.4,
                wasde_corn_for_ethanol_mbu=5400.0,
            )
        )
        # Margin drifts upward by $0.01 per day → forward moves are positive
        # and deterministic, which pins the summary math.
        margins.append(
            ComputedMarginRow(
                obs_date=obs,
                margin_per_bushel=1.0 + 0.01 * i,
                margin_per_gallon=(1.0 + 0.01 * i) / 2.8,
                z_score=0.0,
                signal_label="normal",
                corn_oil_included=True,
            )
        )
    return merged, margins


@pytest.mark.unit
def test_backtester_does_not_pass_future_history_to_rule() -> None:
    """
    The single most important invariant: each replay step gets a truncated
    history slice. If a rule sees a future date in its `history` arg, we have
    lookahead bias and every downstream number is wrong.
    """
    merged, margins = _build_history(400)
    backtester = WarningRuleBacktester(
        _FakeRepo(merged, margins),
        rules=[_LookaheadCanaryRule()],
        expected_directions={"lookahead_canary": "up"},
    )
    reports = backtester.run()
    assert len(reports) == 1
    assert reports[0].fire_count == 0  # canary should never fire; no leak


@pytest.mark.unit
def test_event_cooldown_collapses_consecutive_firings() -> None:
    """
    An always-fire rule over N days should not produce N firings — the 30-day
    cooldown dedupes them into one firing per regime.
    """
    merged, margins = _build_history(400)
    backtester = WarningRuleBacktester(
        _FakeRepo(merged, margins),
        rules=[_AlwaysFireRule()],
        expected_directions={"always_fire": "up"},
    )
    reports = backtester.run()
    fires = reports[0].fire_count
    # 400 days - 200 warmup = 200 replay days.
    # Cooldown 30 days between fires → ~7 firings (200 / 30 rounded).
    assert 5 <= fires <= 8, f"expected ~7 firings after 30d cooldown, got {fires}"


@pytest.mark.unit
def test_hit_rate_and_median_computed_correctly() -> None:
    """
    Margin drifts up $0.01/day, so at any trigger the 30d forward move is +$0.30
    and hit rate for expected_direction='up' should be 100%.
    """
    merged, margins = _build_history(400)
    backtester = WarningRuleBacktester(
        _FakeRepo(merged, margins),
        rules=[_AlwaysFireRule()],
        expected_directions={"always_fire": "up"},
    )
    report = backtester.run()[0]
    assert report.hit_rate_by_horizon[30] == pytest.approx(1.0)
    assert report.median_move_by_horizon[30] == pytest.approx(0.30, abs=0.01)


@pytest.mark.unit
def test_wrong_direction_expectation_flips_hit_rate() -> None:
    """Sanity check the direction wiring: expect 'down' on a rising series → 0% hits."""
    merged, margins = _build_history(400)
    backtester = WarningRuleBacktester(
        _FakeRepo(merged, margins),
        rules=[_AlwaysFireRule()],
        expected_directions={"always_fire": "down"},
    )
    report = backtester.run()[0]
    assert report.hit_rate_by_horizon[30] == pytest.approx(0.0)


@pytest.mark.unit
def test_no_firings_produces_none_stats_not_crash() -> None:
    """A rule that never fires should produce a report with fire_count=0 and no stats."""
    class _NeverFire(WarningRule):
        @property
        def signal_type(self) -> str:
            return "never_fire"

        def evaluate(self, *_args, **_kwargs):
            return None

    merged, margins = _build_history(400)
    backtester = WarningRuleBacktester(
        _FakeRepo(merged, margins),
        rules=[_NeverFire()],
        expected_directions={"never_fire": "up"},
    )
    report = backtester.run()[0]
    assert report.fire_count == 0
    assert report.median_move_by_horizon[30] is None
    assert report.hit_rate_by_horizon[30] is None
