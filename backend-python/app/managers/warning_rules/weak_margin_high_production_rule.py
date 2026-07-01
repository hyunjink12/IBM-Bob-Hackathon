"""Warning when weak margins coincide with elevated ethanol production."""

from __future__ import annotations

from app.managers.warning_rules.base_rule import WarningRule, WarningSignal
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow


class WeakMarginHighProductionRule(WarningRule):
    """
    Flags run-cut risk when economics are soft but production is still high.

    Casual: plants might slow down if they're losing money but still running hard.
    """

    @property
    def signal_type(self) -> str:
        return "weak_margin_high_production"

    def evaluate(
        self,
        latest_row: MergedDailyRow,
        margin_row: ComputedMarginRow,
        history: list[MergedDailyRow],
        margin_history: list[ComputedMarginRow],
    ) -> WarningSignal | None:
        if margin_row.signal_label not in {"weak", "soft"}:
            return None
        if latest_row.ethanol_production_mbpd is None:
            return None
        if not self._production_elevated(history, latest_row.ethanol_production_mbpd):
            return None
        return WarningSignal(
            signal_type=self.signal_type,
            severity="medium",
            message=(
                "Crush margins are weak while ethanol production remains elevated. "
                "Run-rate cuts may be ahead, tightening ethanol supply."
            ),
            metadata={"production_mbpd": latest_row.ethanol_production_mbpd},
        )

    @staticmethod
    def _production_elevated(
        history: list[MergedDailyRow],
        current_production: float,
        lookback_days: int = 180,
    ) -> bool:
        rows = [
            row.ethanol_production_mbpd
            for row in history[-lookback_days:]
            if row.ethanol_production_mbpd is not None
        ]
        if len(rows) < 20:
            return False
        average_production = sum(rows) / len(rows)
        return current_production >= average_production
