"""Crush margin math using Iowa State CARD assumptions."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import MergedDailyRow


@dataclass(frozen=True)
class CrushMarginResult:
    """
    Margin output for one merged daily row.

    `plant_operating_margin` is the physical-only P&L (ethanol + coproduct
    revenue minus corn + gas + opex costs). It's what the plant realizes from
    the crush itself, without any regulatory-value pass-through assumption.

    `d6_rin_value` is the market value of the D6 RIN attached to the ethanol
    output, derived from EPA transaction prices. It's shown as the regulatory
    scale associated with the gallon — the model does NOT assume the producer
    captures this dollar-for-dollar as revenue (that depends on pass-through
    to obligated parties, which is out of scope for this dashboard).

    `margin_per_bushel` retained for existing DuckDB rows and the historical
    z-score / warning-rule signal series — it equals `plant_operating_margin`
    under the new semantic. Consumers rendering "plant margin" should read
    `plant_operating_margin`; consumers rendering the RIN scale should read
    `d6_rin_value` separately.
    """

    plant_operating_margin: float
    plant_operating_margin_per_gallon: float
    d6_rin_value_per_bushel: float
    d6_rin_value_per_gallon: float
    margin_per_bushel: float                # == plant_operating_margin (compat)
    margin_per_gallon: float                # == plant_operating_margin_per_gallon (compat)
    corn_oil_included: bool
    rin_included: bool = False


@dataclass(frozen=True)
class CrushSpreadResult:
    """
    Simple ethanol/corn spread components for one merged daily row.

    Two-leg screen spread: ethanol value per bushel minus corn cost. Coproducts
    (DDGS, corn oil), operating costs, and D6 RIN value are all excluded. This
    is NOT the CME-listed corn-for-ethanol crush contract — it's a simplified
    two-leg dislocation gauge. See `CrushMarginCalculator.calculate_spread`.
    """

    spread_usd_per_bushel: float
    ethanol_leg_usd_per_bushel: float
    corn_leg_usd_per_bushel: float


@dataclass(frozen=True)
class MarginComposition:
    """
    Per-component breakdown of the crush economics in $/bu of corn.

    Casual: what each lever contributes to today's plant P&L, with the D6 RIN
    regulatory value tracked as a separate layer beside the physical margin.

    Physical fields (ethanol/ddgs/corn_oil/corn/gas/opex) sum to
    `plant_operating_margin` in CrushMarginResult. `d6_rin_value` is the
    regulatory-compliance market value associated with the ethanol output —
    kept out of the physical sum so the UI can present them independently
    without implying dollar-for-dollar producer capture.
    """

    ethanol_revenue: float
    ddgs_revenue: float
    corn_oil_revenue: float
    d6_rin_value: float                    # regulatory layer, NOT summed into plant margin
    corn_cost: float
    nat_gas_cost: float
    misc_opex_cost: float
    corn_oil_included: bool
    rin_included: bool


class CrushMarginCalculator:
    """
    Turns market inputs into crush margin per bushel and per gallon.

    Casual: did the plant make money today or not?

    Applies CARD yields with DDGS quoted in $/short ton (converted internally).
    Corn oil revenue is included only when a price is present on the merged row.
    """

    def __init__(self, model_config: CrushModelConfig) -> None:
        self._config = model_config

    def calculate(self, row: MergedDailyRow) -> CrushMarginResult | None:
        """
        Compute crush margin for one day.

        Returns None when required price inputs are missing.
        """
        if not self._has_required_inputs(row):
            return None

        ethanol_revenue = row.ethanol_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        ddgs_revenue = self._config.ddgs_revenue_per_bushel(row.ddgs_usd_per_short_ton)
        corn_oil_included = row.corn_oil_usd_per_pound is not None
        corn_oil_revenue = 0.0
        if corn_oil_included:
            corn_oil_revenue = (
                row.corn_oil_usd_per_pound * self._config.corn_oil_pounds_per_bushel
            )
        rin_included = row.d6_rin_usd_per_gallon is not None
        # D6 RIN value is a REGULATORY/COMPLIANCE market value, not producer
        # revenue. Kept out of the physical-margin sum so a "RICH margin"
        # signal reflects physical-crush economics rather than compliance-market
        # moves (which respond to different information — EPA rulings, SREs).
        d6_rin_value_per_bushel = (
            row.d6_rin_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        ) if rin_included else 0.0

        total_physical_revenue = ethanol_revenue + ddgs_revenue + corn_oil_revenue
        corn_cost = row.corn_usd_per_bushel
        gas_cost = row.nat_gas_usd_per_mmbtu * self._config.natural_gas_mmbtu_per_bushel
        misc_cost = self._config.misc_opex_per_bushel

        plant_operating_margin = total_physical_revenue - corn_cost - gas_cost - misc_cost
        plant_operating_margin_per_gallon = plant_operating_margin / self._config.ethanol_gallons_per_bushel
        d6_rin_value_per_gallon = (
            row.d6_rin_usd_per_gallon if rin_included else 0.0
        )

        return CrushMarginResult(
            plant_operating_margin=plant_operating_margin,
            plant_operating_margin_per_gallon=plant_operating_margin_per_gallon,
            d6_rin_value_per_bushel=d6_rin_value_per_bushel,
            d6_rin_value_per_gallon=d6_rin_value_per_gallon,
            # `margin_per_bushel` retained as an alias for the physical margin so
            # historical `computed_margins` rows and z-score series remain a
            # coherent physical-economics signal, not a compliance mix.
            margin_per_bushel=plant_operating_margin,
            margin_per_gallon=plant_operating_margin_per_gallon,
            corn_oil_included=corn_oil_included,
            rin_included=rin_included,
        )

    def decompose(self, row: MergedDailyRow) -> MarginComposition | None:
        """
        Break the crush margin into its six line-item drivers.

        Casual: same math as `calculate()` but keeps every piece separate so
        the UI can show what's driving the number.

        Costs are returned as negative numbers so the frontend can render them
        directly against the revenue bars without extra sign-flipping.
        """
        if not self._has_required_inputs(row):
            return None

        ethanol_revenue = row.ethanol_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        ddgs_revenue = self._config.ddgs_revenue_per_bushel(row.ddgs_usd_per_short_ton)
        corn_oil_included = row.corn_oil_usd_per_pound is not None
        corn_oil_revenue = 0.0
        if corn_oil_included:
            corn_oil_revenue = (
                row.corn_oil_usd_per_pound * self._config.corn_oil_pounds_per_bushel
            )
        rin_included = row.d6_rin_usd_per_gallon is not None
        d6_rin_value = (
            row.d6_rin_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        ) if rin_included else 0.0

        return MarginComposition(
            ethanol_revenue=ethanol_revenue,
            ddgs_revenue=ddgs_revenue,
            corn_oil_revenue=corn_oil_revenue,
            d6_rin_value=d6_rin_value,
            corn_cost=-row.corn_usd_per_bushel,
            nat_gas_cost=-(row.nat_gas_usd_per_mmbtu * self._config.natural_gas_mmbtu_per_bushel),
            misc_opex_cost=-self._config.misc_opex_per_bushel,
            corn_oil_included=corn_oil_included,
            rin_included=rin_included,
        )

    def calculate_spread(self, row: MergedDailyRow) -> CrushSpreadResult | None:
        """
        Simple ethanol/corn spread in $/bu-corn: 2.8 × ethanol − corn.

        Two-leg screen spread: uses the CARD dry-mill yield
        (ethanol_gallons_per_bushel) so ethanol $/gal and corn $/bu resolve
        to the same unit ($/bu of corn). Coproducts (DDGS, corn oil),
        operating costs (gas, opex), and the D6 RIN regulatory value are all
        excluded on purpose — the richer physical view is in `calculate()`.

        This is NOT the exchange-listed corn-for-ethanol crush contract; it's
        a simplified two-leg dislocation gauge useful as a screen for the
        primary input/output relationship.
        """
        if row.corn_usd_per_bushel is None or row.ethanol_usd_per_gallon is None:
            return None
        ethanol_leg = row.ethanol_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        corn_leg = row.corn_usd_per_bushel
        return CrushSpreadResult(
            spread_usd_per_bushel=ethanol_leg - corn_leg,
            ethanol_leg_usd_per_bushel=ethanol_leg,
            corn_leg_usd_per_bushel=corn_leg,
        )

    @staticmethod
    def _has_required_inputs(row: MergedDailyRow) -> bool:
        required = (
            row.corn_usd_per_bushel,
            row.ethanol_usd_per_gallon,
            row.ddgs_usd_per_short_ton,
            row.nat_gas_usd_per_mmbtu,
        )
        return all(value is not None for value in required)
