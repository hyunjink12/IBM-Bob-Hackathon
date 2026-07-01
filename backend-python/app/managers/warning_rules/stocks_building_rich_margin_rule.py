"""Warning when ethanol stocks build while crush margins stay rich."""

from __future__ import annotations

from app.managers.warning_rules.base_rule import WarningRule, WarningSignal
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


class StocksBuildingRichMarginRule(WarningRule):
    """
    Flags inventory builds against strong plant economics.

    Casual: plants are making money but tanks are filling up anyway.
    """

    @property
    def signal_type(self) -> str:
        return "stocks_building_rich_margin"

    def evaluate(
        self,
        latest_row: MergedDailyRow,
        margin_row: ComputedMarginRow,
        history: list[MergedDailyRow],
        margin_history: list[ComputedMarginRow],
    ) -> WarningSignal | None:
        if margin_row.signal_label not in {"rich", "elevated"}:
            return None
        if not self._stocks_building(history):
            return None
        return WarningSignal(
            signal_type=self.signal_type,
            severity="high",
            message=(
                "Ethanol inventories are building while crush margins remain strong. "
                "Production may be outpacing blending demand."
            ),
            metadata={"signal_label": margin_row.signal_label},
        )

    @staticmethod
    def _stocks_building(history: list[MergedDailyRow], lookback_days: int = 28) -> bool:
        rows_with_stocks = [row for row in history if row.ethanol_stocks_mmbbl is not None]
        if len(rows_with_stocks) < lookback_days + 1:
            return False
        recent = rows_with_stocks[-1].ethanol_stocks_mmbbl
        prior = rows_with_stocks[-lookback_days - 1].ethanol_stocks_mmbbl
        return recent is not None and prior is not None and recent > prior * 1.02
