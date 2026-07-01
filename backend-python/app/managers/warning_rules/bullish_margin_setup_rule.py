"""Warning for bullish margin setup: cheap corn, strong RBOB, low ethanol stocks."""

from __future__ import annotations

from app.managers.warning_rules.base_rule import WarningRule, WarningSignal
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


class BullishMarginSetupRule(WarningRule):
    """
    Flags supportive blending and feedstock backdrop for ethanol margins.

    Casual: cheap corn, strong gasoline, and tight ethanol stocks = friendly setup.
    """

    @property
    def signal_type(self) -> str:
        return "bullish_margin_setup"

    def evaluate(
        self,
        latest_row: MergedDailyRow,
        margin_row: ComputedMarginRow,
        history: list[MergedDailyRow],
        margin_history: list[ComputedMarginRow],
    ) -> WarningSignal | None:
        if any(
            value is None
            for value in (
                latest_row.corn_usd_per_bushel,
                latest_row.rbob_usd_per_gallon,
                latest_row.ethanol_stocks_mmbbl,
            )
        ):
            return None

        if not self._corn_cheap(history, latest_row.corn_usd_per_bushel):
            return None
        if not self._rbob_strong(history, latest_row.rbob_usd_per_gallon):
            return None
        if not self._stocks_low(history, latest_row.ethanol_stocks_mmbbl):
            return None

        return WarningSignal(
            signal_type=self.signal_type,
            severity="medium",
            message=(
                "Corn is cheap, RBOB is strong, and ethanol stocks are low. "
                "Blending economics and feedstock costs support higher run rates."
            ),
            metadata={
                "corn_usd_per_bushel": latest_row.corn_usd_per_bushel,
                "rbob_usd_per_gallon": latest_row.rbob_usd_per_gallon,
                "ethanol_stocks_mmbbl": latest_row.ethanol_stocks_mmbbl,
            },
        )

    @staticmethod
    def _corn_cheap(history: list[MergedDailyRow], current: float, lookback: int = 180) -> bool:
        values = [
            row.corn_usd_per_bushel
            for row in history[-lookback:]
            if row.corn_usd_per_bushel is not None
        ]
        if len(values) < 20:
            return False
        return current <= sum(values) / len(values)

    @staticmethod
    def _rbob_strong(history: list[MergedDailyRow], current: float, lookback: int = 180) -> bool:
        values = [
            row.rbob_usd_per_gallon
            for row in history[-lookback:]
            if row.rbob_usd_per_gallon is not None
        ]
        if len(values) < 20:
            return False
        return current >= sum(values) / len(values)

    @staticmethod
    def _stocks_low(history: list[MergedDailyRow], current: float, lookback: int = 180) -> bool:
        values = [
            row.ethanol_stocks_mmbbl
            for row in history[-lookback:]
            if row.ethanol_stocks_mmbbl is not None
        ]
        if len(values) < 20:
            return False
        return current <= sum(values) / len(values)
