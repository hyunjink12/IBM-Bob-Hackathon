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
def test_spread_matches_cme_crush_formula(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    calculator = CrushMarginCalculator(crush_config)
    spread = calculator.calculate_spread(sample_row)
    assert spread is not None

    expected_ethanol_leg = (
        sample_row.ethanol_usd_per_gallon * crush_config.ethanol_gallons_per_bushel
    )
    expected_corn_leg = sample_row.corn_usd_per_bushel
    assert spread.ethanol_leg_usd_per_bushel == pytest.approx(expected_ethanol_leg)
    assert spread.corn_leg_usd_per_bushel == pytest.approx(expected_corn_leg)
    assert spread.spread_usd_per_bushel == pytest.approx(
        expected_ethanol_leg - expected_corn_leg
    )


@pytest.mark.unit
def test_spread_ignores_coproducts_and_costs(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    """The CME crush spread must not depend on DDGS, corn oil, gas, or opex."""
    calculator = CrushMarginCalculator(crush_config)
    baseline = calculator.calculate_spread(sample_row)
    perturbed_row = MergedDailyRow(
        **{
            **sample_row.__dict__,
            "ddgs_usd_per_short_ton": sample_row.ddgs_usd_per_short_ton * 2,
            "corn_oil_usd_per_pound": None,
            "nat_gas_usd_per_mmbtu": sample_row.nat_gas_usd_per_mmbtu * 3,
        }
    )
    perturbed = calculator.calculate_spread(perturbed_row)
    assert baseline is not None and perturbed is not None
    assert baseline.spread_usd_per_bushel == pytest.approx(perturbed.spread_usd_per_bushel)


@pytest.mark.unit
def test_spread_returns_none_when_price_leg_missing(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    calculator = CrushMarginCalculator(crush_config)
    missing_ethanol = MergedDailyRow(
        **{**sample_row.__dict__, "ethanol_usd_per_gallon": None}
    )
    missing_corn = MergedDailyRow(
        **{**sample_row.__dict__, "corn_usd_per_bushel": None}
    )
    assert calculator.calculate_spread(missing_ethanol) is None
    assert calculator.calculate_spread(missing_corn) is None
