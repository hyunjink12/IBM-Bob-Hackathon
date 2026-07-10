"""Warning for bullish margin setup: cheap corn, strong RBOB, low ethanol stocks."""

from __future__ import annotations

from app.managers.warning_rules.base_rule import WarningRule, WarningSignal
from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow

_LOW_PERCENTILE = 0.20
_HIGH_PERCENTILE = 0.80
_LOOKBACK_DAYS = 180
_MIN_OBSERVATIONS = 60


class BullishMarginSetupRule(WarningRule):
    """
    Flags supportive blending and feedstock backdrop for ethanol margins.

    Casual: cheap corn, strong gasoline, and tight ethanol stocks = friendly setup.

    Uses 20th/80th percentiles rather than a rolling mean so the rule only fires
    at genuine tail conditions, not on ~half of trading days.
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
                "Corn is in the bottom 20% of its 180-day range, RBOB is in the top 20%, "
                "and ethanol stocks are in the bottom 20%. Blending economics and feedstock "
                "costs both support higher run rates."
            ),
            suggested_trade=(
                "Long ethanol / long corn demand. Spread trade: long the ethanol margin, "
                "long corn futures if stronger grind demand is not yet priced in."
            ),
            metadata={
                "corn_usd_per_bushel": latest_row.corn_usd_per_bushel,
                "rbob_usd_per_gallon": latest_row.rbob_usd_per_gallon,
                "ethanol_stocks_mmbbl": latest_row.ethanol_stocks_mmbbl,
            },
        )

    @staticmethod
    def _corn_cheap(history: list[MergedDailyRow], current: float) -> bool:
        values = [
            row.corn_usd_per_bushel
            for row in history[-_LOOKBACK_DAYS:]
            if row.corn_usd_per_bushel is not None
        ]
        if len(values) < _MIN_OBSERVATIONS:
            return False
        return current <= _percentile(values, _LOW_PERCENTILE)

    @staticmethod
    def _rbob_strong(history: list[MergedDailyRow], current: float) -> bool:
        values = [
            row.rbob_usd_per_gallon
            for row in history[-_LOOKBACK_DAYS:]
            if row.rbob_usd_per_gallon is not None
        ]
        if len(values) < _MIN_OBSERVATIONS:
            return False
        return current >= _percentile(values, _HIGH_PERCENTILE)

    @staticmethod
    def _stocks_low(history: list[MergedDailyRow], current: float) -> bool:
        values = [
            row.ethanol_stocks_mmbbl
            for row in history[-_LOOKBACK_DAYS:]
            if row.ethanol_stocks_mmbbl is not None
        ]
        if len(values) < _MIN_OBSERVATIONS:
            return False
        return current <= _percentile(values, _LOW_PERCENTILE)


def _percentile(values: list[float], fraction: float) -> float:
    """Linear-interp percentile without pulling in numpy."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile called on empty list")
    rank = fraction * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
