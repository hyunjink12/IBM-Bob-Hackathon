"""Unit tests for warning signal rules."""

from datetime import date, timedelta

import pytest

from app.managers.warning_rules.bullish_margin_setup_rule import BullishMarginSetupRule
from app.managers.warning_rules.stocks_building_rich_margin_rule import (
    StocksBuildingRichMarginRule,
)
from app.managers.warning_rules.weak_margin_high_production_rule import (
    WeakMarginHighProductionRule,
)
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


def _history(length: int, **overrides) -> list[MergedDailyRow]:
    """
    Build a merged-daily history with a triangular wave so percentile checks
    have real dispersion. Flat histories collapse 20th/median/80th to the same
    value, which would let equality-at-tails pass the guards trivially.
    """
    rows = []
    for index in range(length):
        # Wave amplitude ±10% around the base level, period 40 days.
        wave = ((index % 40) - 20) / 200.0  # roughly −0.10 to +0.10 fraction
        rows.append(
            MergedDailyRow(
                obs_date=date(2024, 1, 1) + timedelta(days=index),
                corn_usd_per_bushel=overrides.get("corn", 5.0) * (1 + wave),
                ethanol_usd_per_gallon=1.8,
                ddgs_usd_per_short_ton=150.0,
                rbob_usd_per_gallon=overrides.get("rbob", 2.0) * (1 + wave),
                nat_gas_usd_per_mmbtu=2.5,
                ethanol_stocks_mmbbl=overrides.get("stocks", 22.0) * (1 + wave),
                ethanol_production_mbpd=overrides.get("production", 1000.0) * (1 + wave),
                corn_oil_usd_per_pound=0.4,
                wasde_corn_for_ethanol_mbu=5400.0,
            )
        )
    return rows


@pytest.mark.unit
def test_stocks_building_rich_margin_rule_fires() -> None:
    history = _history(60)
    # Rule compares to lookback (28d) prior stocks — force the last day 10%
    # above that specific reference so the 2% build threshold is cleared.
    reference = history[-29].ethanol_stocks_mmbbl
    history[-1] = MergedDailyRow(
        **{
            **history[-1].__dict__,
            "ethanol_stocks_mmbbl": reference * 1.10,
        }
    )
    latest = history[-1]
    margin = ComputedMarginRow(
        obs_date=latest.obs_date,
        margin_per_bushel=1.0,
        margin_per_gallon=0.35,
        z_score=2.0,
        signal_label="rich",
        corn_oil_included=True,
    )
    signal = StocksBuildingRichMarginRule().evaluate(latest, margin, history, [])
    assert signal is not None
    assert signal.signal_type == "stocks_building_rich_margin"
    assert signal.suggested_trade  # abstract's "Possible trade" line is populated


@pytest.mark.unit
def test_bullish_setup_requires_20th_pct_corn_80th_pct_rbob_20th_pct_stocks() -> None:
    # 200 days flat at typical levels; latest breaches all three tails.
    history = _history(200, corn=5.5, rbob=2.0, stocks=25.0)
    latest = MergedDailyRow(
        **{
            **history[-1].__dict__,
            "corn_usd_per_bushel": 4.0,      # far below 20th pct of 5.5
            "rbob_usd_per_gallon": 2.8,      # far above 80th pct of 2.0
            "ethanol_stocks_mmbbl": 18.0,    # below 20th pct of ~25
        }
    )
    margin = ComputedMarginRow(
        obs_date=latest.obs_date,
        margin_per_bushel=0.5,
        margin_per_gallon=0.2,
        z_score=0.5,
        signal_label="normal",
        corn_oil_included=True,
    )
    signal = BullishMarginSetupRule().evaluate(latest, margin, history, [])
    assert signal is not None
    assert signal.suggested_trade


@pytest.mark.unit
def test_bullish_setup_does_not_fire_at_median() -> None:
    """Median-level inputs should NOT fire the rule (percentile guard)."""
    history = _history(200, corn=5.5, rbob=2.0, stocks=25.0)
    # Latest sits at the middle of the wave — corn/rbob/stocks all at their base
    # (median) level, so no tail is breached.
    latest = MergedDailyRow(
        **{
            **history[-1].__dict__,
            "corn_usd_per_bushel": 5.5,
            "rbob_usd_per_gallon": 2.0,
            "ethanol_stocks_mmbbl": 25.0,
        }
    )
    margin = ComputedMarginRow(
        obs_date=latest.obs_date,
        margin_per_bushel=0.5,
        margin_per_gallon=0.2,
        z_score=0.5,
        signal_label="normal",
        corn_oil_included=True,
    )
    signal = BullishMarginSetupRule().evaluate(latest, margin, history, [])
    assert signal is None


@pytest.mark.unit
def test_weak_margin_high_production_uses_80th_percentile() -> None:
    """Production must be in the top 20% of history, not just above the mean."""
    history_low = _history(200, production=900.0)
    # A day with production RIGHT AT the base level should NOT fire.
    latest_median = MergedDailyRow(
        **{**history_low[-1].__dict__, "ethanol_production_mbpd": 900.0}
    )
    margin_soft = ComputedMarginRow(
        obs_date=latest_median.obs_date,
        margin_per_bushel=-0.2,
        margin_per_gallon=-0.07,
        z_score=-1.2,
        signal_label="soft",
        corn_oil_included=True,
    )
    assert (
        WeakMarginHighProductionRule().evaluate(
            latest_median, margin_soft, history_low, []
        )
        is None
    )

    # A day well into the top decile should fire.
    latest_hot = MergedDailyRow(
        **{**history_low[-1].__dict__, "ethanol_production_mbpd": 1200.0}
    )
    signal = WeakMarginHighProductionRule().evaluate(
        latest_hot, margin_soft, history_low, []
    )
    assert signal is not None
    assert signal.suggested_trade
