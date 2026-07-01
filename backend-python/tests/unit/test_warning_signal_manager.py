"""Unit tests for warning signal rules."""

from datetime import date, timedelta

import pytest

from app.managers.warning_rules.bullish_margin_setup_rule import BullishMarginSetupRule
from app.managers.warning_rules.stocks_building_rich_margin_rule import (
    StocksBuildingRichMarginRule,
)
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


def _history(length: int, **overrides) -> list[MergedDailyRow]:
    rows = []
    for index in range(length):
        rows.append(
            MergedDailyRow(
                obs_date=date(2024, 1, 1) + timedelta(days=index),
                corn_usd_per_bushel=overrides.get("corn", 5.0),
                ethanol_usd_per_gallon=1.8,
                ddgs_usd_per_short_ton=150.0,
                rbob_usd_per_gallon=overrides.get("rbob", 2.0),
                nat_gas_usd_per_mmbtu=2.5,
                ethanol_stocks_mmbbl=overrides.get("stocks", 20.0 + index * 0.01),
                ethanol_production_mbpd=1000.0,
                corn_oil_usd_per_pound=0.4,
                wasde_corn_for_ethanol_mbu=5400.0,
            )
        )
    return rows


@pytest.mark.unit
def test_stocks_building_rich_margin_rule_fires() -> None:
    history = _history(60)
    history[-1] = MergedDailyRow(
        **{
            **history[-1].__dict__,
            "ethanol_stocks_mmbbl": history[0].ethanol_stocks_mmbbl * 1.1,
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


@pytest.mark.unit
def test_bullish_setup_requires_cheap_corn_strong_rbob_low_stocks() -> None:
    history = _history(200, corn=5.5, rbob=2.0, stocks=25.0)
    latest = MergedDailyRow(
        **{
            **history[-1].__dict__,
            "corn_usd_per_bushel": 4.0,
            "rbob_usd_per_gallon": 2.8,
            "ethanol_stocks_mmbbl": 18.0,
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
