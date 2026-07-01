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
    ethanol_net_per_bushel: float


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

        total_revenue = ethanol_revenue + ddgs_revenue + corn_oil_revenue
        corn_cost = row.corn_usd_per_bushel
        gas_cost = row.nat_gas_usd_per_mmbtu * self._config.natural_gas_mmbtu_per_bushel
        misc_cost = self._config.misc_opex_per_bushel

        margin_per_bushel = total_revenue - corn_cost - gas_cost - misc_cost
        margin_per_gallon = margin_per_bushel / self._config.ethanol_gallons_per_bushel
        ethanol_net_per_bushel = total_revenue / self._config.ethanol_gallons_per_bushel

        return CrushMarginResult(
            margin_per_bushel=margin_per_bushel,
            margin_per_gallon=margin_per_gallon,
            corn_oil_included=corn_oil_included,
            ethanol_net_per_bushel=ethanol_net_per_bushel,
        )

    def calculate_spread(self, row: MergedDailyRow) -> float | None:
        """Net ethanol value per bushel minus corn futures price."""
        margin = self.calculate(row)
        if margin is None or row.corn_usd_per_bushel is None:
            return None
        return margin.ethanol_net_per_bushel - row.corn_usd_per_bushel

    @staticmethod
    def _has_required_inputs(row: MergedDailyRow) -> bool:
        required = (
            row.corn_usd_per_bushel,
            row.ethanol_usd_per_gallon,
            row.ddgs_usd_per_short_ton,
            row.nat_gas_usd_per_mmbtu,
        )
        return all(value is not None for value in required)
