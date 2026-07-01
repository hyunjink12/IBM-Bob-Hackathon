"""Unit tests for crush margin calculator."""

from datetime import date

import pytest

from app.managers.crush_margin_calculator import CrushMarginCalculator
from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import MergedDailyRow


@pytest.fixture
def crush_config() -> CrushModelConfig:
    return CrushModelConfig(
        ethanol_gallons_per_bushel=2.8,
        ddgs_pounds_per_bushel=17,
        corn_oil_pounds_per_bushel=0.7,
        natural_gas_mmbtu_per_bushel=0.0728,
        misc_opex_per_bushel=0.35,
    )


@pytest.fixture
def sample_row() -> MergedDailyRow:
    return MergedDailyRow(
        obs_date=date(2024, 6, 1),
        corn_usd_per_bushel=4.5,
        ethanol_usd_per_gallon=1.9,
        ddgs_usd_per_short_ton=160.0,
        rbob_usd_per_gallon=2.4,
        nat_gas_usd_per_mmbtu=2.5,
        ethanol_stocks_mmbbl=22.0,
        ethanol_production_mbpd=1000.0,
        corn_oil_usd_per_pound=0.4,
        wasde_corn_for_ethanol_mbu=5400.0,
    )


@pytest.mark.unit
def test_crush_margin_positive_with_sample_inputs(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    calculator = CrushMarginCalculator(crush_config)
    result = calculator.calculate(sample_row)
    assert result is not None
    assert result.corn_oil_included is True
    assert result.margin_per_gallon == pytest.approx(
        result.margin_per_bushel / crush_config.ethanol_gallons_per_bushel
    )
    assert result.margin_per_bushel > 0


@pytest.mark.unit
def test_ddgs_uses_short_ton_not_per_pound(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    calculator = CrushMarginCalculator(crush_config)
    with_oil = calculator.calculate(sample_row)
    without_oil_row = MergedDailyRow(
        **{**sample_row.__dict__, "corn_oil_usd_per_pound": None}
    )
    without_oil = calculator.calculate(without_oil_row)
    assert with_oil is not None and without_oil is not None
    assert with_oil.margin_per_bushel > without_oil.margin_per_bushel


@pytest.mark.unit
def test_spread_is_net_ethanol_minus_corn(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    calculator = CrushMarginCalculator(crush_config)
    spread = calculator.calculate_spread(sample_row)
    result = calculator.calculate(sample_row)
    assert spread is not None and result is not None
    assert spread == pytest.approx(result.ethanol_net_per_bushel - sample_row.corn_usd_per_bushel)
