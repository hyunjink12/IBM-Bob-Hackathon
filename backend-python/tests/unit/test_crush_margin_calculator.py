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
def test_rin_revenue_lifts_margin_by_exactly_rin_price_times_yield(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    """RIN present must add exactly (rin_price × 2.8) to $/bu margin."""
    calculator = CrushMarginCalculator(crush_config)
    without_rin = calculator.calculate(sample_row)
    with_rin_row = MergedDailyRow(
        **{**sample_row.__dict__, "d6_rin_usd_per_gallon": 0.60}
    )
    with_rin = calculator.calculate(with_rin_row)
    assert without_rin is not None and with_rin is not None
    assert without_rin.rin_included is False
    assert with_rin.rin_included is True
    expected_lift = 0.60 * crush_config.ethanol_gallons_per_bushel
    assert with_rin.margin_per_bushel == pytest.approx(
        without_rin.margin_per_bushel + expected_lift
    )


@pytest.mark.unit
def test_rin_missing_leaves_calculation_identical_to_pre_rin_math(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    """Backward compat: sample_row has no RIN → margin math must be unchanged."""
    calculator = CrushMarginCalculator(crush_config)
    result = calculator.calculate(sample_row)
    assert result is not None
    assert result.rin_included is False
    # Recompute the pre-RIN expression by hand and compare
    ethanol_rev = sample_row.ethanol_usd_per_gallon * crush_config.ethanol_gallons_per_bushel
    ddgs_rev = crush_config.ddgs_revenue_per_bushel(sample_row.ddgs_usd_per_short_ton)
    corn_oil_rev = sample_row.corn_oil_usd_per_pound * crush_config.corn_oil_pounds_per_bushel
    corn_cost = sample_row.corn_usd_per_bushel
    gas_cost = sample_row.nat_gas_usd_per_mmbtu * crush_config.natural_gas_mmbtu_per_bushel
    expected = ethanol_rev + ddgs_rev + corn_oil_rev - corn_cost - gas_cost - crush_config.misc_opex_per_bushel
    assert result.margin_per_bushel == pytest.approx(expected)


@pytest.mark.unit
def test_margin_composition_sums_to_margin_per_bushel_with_rin(
    crush_config: CrushModelConfig,
    sample_row: MergedDailyRow,
) -> None:
    """decompose() lines must sum to calculate() total, including the RIN line."""
    calculator = CrushMarginCalculator(crush_config)
    with_rin_row = MergedDailyRow(
        **{**sample_row.__dict__, "d6_rin_usd_per_gallon": 0.55}
    )
    result = calculator.calculate(with_rin_row)
    comp = calculator.decompose(with_rin_row)
    assert result is not None and comp is not None
    component_sum = (
        comp.ethanol_revenue + comp.ddgs_revenue + comp.corn_oil_revenue
        + comp.rin_revenue + comp.corn_cost + comp.nat_gas_cost + comp.misc_opex_cost
    )
    assert component_sum == pytest.approx(result.margin_per_bushel)


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
