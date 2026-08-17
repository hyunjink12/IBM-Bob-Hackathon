"""Crush margin math using Iowa State CARD assumptions."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.crush_model_config import CrushModelConfig
from app.storage.duckdb_repository import MergedDailyRow


@dataclass(frozen=True)
class CrushMarginResult:
    """Margin output for one merged daily row."""

    margin_per_bushel: float
    margin_per_gallon: float
    corn_oil_included: bool
    rin_included: bool = False


@dataclass(frozen=True)
class CrushSpreadResult:
    """CME-standard ethanol crush spread components for one merged daily row."""

    spread_usd_per_bushel: float
    ethanol_leg_usd_per_bushel: float
    corn_leg_usd_per_bushel: float


@dataclass(frozen=True)
class MarginComposition:
    """
    Per-component breakdown of the crush margin in $/bu of corn.

    Casual: what each lever contributes to today's margin.

    Positive numbers are revenue contributions; negative are cost contributions.
    Sum of all fields (except the *_included flags) equals `margin_per_bushel`
    in CrushMarginResult. RIN revenue is only non-zero when a D6 RIN price is
    present on the merged row — flagged by `rin_included` so the UI can
    distinguish "no RIN data" from "RIN data present but zero contribution".
    """

    ethanol_revenue: float
    ddgs_revenue: float
    corn_oil_revenue: float
    rin_revenue: float
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
        rin_revenue = (
            row.d6_rin_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        ) if rin_included else 0.0

        total_revenue = ethanol_revenue + ddgs_revenue + corn_oil_revenue + rin_revenue
        corn_cost = row.corn_usd_per_bushel
        gas_cost = row.nat_gas_usd_per_mmbtu * self._config.natural_gas_mmbtu_per_bushel
        misc_cost = self._config.misc_opex_per_bushel

        margin_per_bushel = total_revenue - corn_cost - gas_cost - misc_cost
        margin_per_gallon = margin_per_bushel / self._config.ethanol_gallons_per_bushel

        return CrushMarginResult(
            margin_per_bushel=margin_per_bushel,
            margin_per_gallon=margin_per_gallon,
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
        rin_revenue = (
            row.d6_rin_usd_per_gallon * self._config.ethanol_gallons_per_bushel
        ) if rin_included else 0.0

        return MarginComposition(
            ethanol_revenue=ethanol_revenue,
            ddgs_revenue=ddgs_revenue,
            corn_oil_revenue=corn_oil_revenue,
            rin_revenue=rin_revenue,
            corn_cost=-row.corn_usd_per_bushel,
            nat_gas_cost=-(row.nat_gas_usd_per_mmbtu * self._config.natural_gas_mmbtu_per_bushel),
            misc_opex_cost=-self._config.misc_opex_per_bushel,
            corn_oil_included=corn_oil_included,
            rin_included=rin_included,
        )

    def calculate_spread(self, row: MergedDailyRow) -> CrushSpreadResult | None:
        """
        CME-standard ethanol crush spread in $/bu-corn: 2.8 × ethanol − corn.

        Uses the CARD dry-mill yield (ethanol_gallons_per_bushel) so that ethanol
        $/gal and corn $/bu resolve to the same unit ($/bu of corn). Coproducts
        (DDGS, corn oil) and costs (gas, opex) are excluded on purpose — that
        richer view is the crush margin in `calculate()`. This spread mirrors the
        exchange-listed crush and is the industry-standard input dislocation gauge.
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
