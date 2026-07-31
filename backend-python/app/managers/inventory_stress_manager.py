"""Builds inventory / production stress context for Panel 4."""

from __future__ import annotations

import logging

from app.storage.duckdb_repository import ComputedMarginRow, MergedDailyRow

_logger = logging.getLogger(__name__)

# Any weekly move above this fraction is almost certainly a unit-mixup or
# a stale/seed row bleeding in — cap and warn rather than render nonsense
# like "+82,286%". Real hurricane weeks might touch 15-20%; 100% is defensive.
_MAX_PLAUSIBLE_STOCKS_CHANGE = 1.00


class InventoryStressManager:
    """
    Summarizes stocks + production pressure for the stress panel.

    Casual: turns raw tanks-and-run-rate numbers into a quick health check.

    Panel 4 used to only show rule-based warning cards, so calm markets looked
    like missing data. This manager always returns a snapshot (levels, deltas,
    and a calm/watch/alert status) so the UI has something concrete to render
    even when no alert rules fire.
    """

    STOCKS_LOOKBACK_DAYS = 28
    PRODUCTION_LOOKBACK_DAYS = 180
    STOCKS_BUILD_THRESHOLD = 0.02

    def build_snapshot(
        self,
        history: list[MergedDailyRow],
        latest_margin: ComputedMarginRow | None,
        active_warning_count: int,
    ) -> dict:
        """
        Build the stress snapshot dict for the warnings API.

        Casual: package stocks, production, and vibe-check status for the UI.

        Pulls the latest merged day, compares stocks vs ~4 weeks ago and
        production vs the trailing average, then labels overall status from
        those deltas plus any active warning cards.
        """
        if not history:
            return self._empty_snapshot()

        latest = history[-1]
        stocks_change_pct = self._stocks_change_pct(history)
        production_vs_avg_pct = self._production_vs_avg_pct(history)
        signal_label = latest_margin.signal_label if latest_margin else None
        status, status_message = self._resolve_status(
            stocks_change_pct=stocks_change_pct,
            production_vs_avg_pct=production_vs_avg_pct,
            signal_label=signal_label,
            active_warning_count=active_warning_count,
        )

        return {
            "stocks_mmbbl": latest.ethanol_stocks_mmbbl,
            "stocks_change_28d_pct": stocks_change_pct,
            "production_mbpd": latest.ethanol_production_mbpd,
            "production_vs_180d_avg_pct": production_vs_avg_pct,
            "margin_signal_label": signal_label,
            "status": status,
            "status_message": status_message,
        }

    def _stocks_change_pct(self, history: list[MergedDailyRow]) -> float | None:
        """
        Percent change in ethanol stocks over the lookback window.

        Casual: are tanks filling or draining vs a month ago?
        """
        rows_with_stocks = [
            row for row in history if row.ethanol_stocks_mmbbl is not None
        ]
        if len(rows_with_stocks) < self.STOCKS_LOOKBACK_DAYS + 1:
            return None

        recent = rows_with_stocks[-1].ethanol_stocks_mmbbl
        prior = rows_with_stocks[-self.STOCKS_LOOKBACK_DAYS - 1].ethanol_stocks_mmbbl
        if recent is None or prior is None or prior == 0:
            return None
        change = (recent - prior) / prior
        if abs(change) > _MAX_PLAUSIBLE_STOCKS_CHANGE:
            _logger.warning(
                "Stocks change %.1f%% over %sd is implausible; likely a unit mismatch "
                "in raw_observations (recent=%.3f, prior=%.3f). Suppressing.",
                change * 100,
                self.STOCKS_LOOKBACK_DAYS,
                recent,
                prior,
            )
            return None
        return change

    def _production_vs_avg_pct(self, history: list[MergedDailyRow]) -> float | None:
        """
        Latest production vs trailing average, as a fraction.

        Casual: are plants running hotter or cooler than usual?
        """
        latest = history[-1]
        if latest.ethanol_production_mbpd is None:
            return None

        values = [
            row.ethanol_production_mbpd
            for row in history[-self.PRODUCTION_LOOKBACK_DAYS :]
            if row.ethanol_production_mbpd is not None
        ]
        if len(values) < 20:
            return None

        average = sum(values) / len(values)
        if average == 0:
            return None
        return (latest.ethanol_production_mbpd - average) / average

    def _resolve_status(
        self,
        *,
        stocks_change_pct: float | None,
        production_vs_avg_pct: float | None,
        signal_label: str | None,
        active_warning_count: int,
    ) -> tuple[str, str]:
        """
        Map metrics + warning count into calm / watch / alert.

        Casual: one word for how spicy inventory/production looks right now.
        """
        if active_warning_count > 0:
            return (
                "alert",
                f"{active_warning_count} active warning signal"
                f"{'s' if active_warning_count != 1 else ''} for the latest session.",
            )

        stocks_building = (
            stocks_change_pct is not None
            and stocks_change_pct > self.STOCKS_BUILD_THRESHOLD
        )
        production_elevated = (
            production_vs_avg_pct is not None and production_vs_avg_pct >= 0
        )
        soft_margins = signal_label in {"soft", "weak"}
        rich_margins = signal_label in {"rich", "elevated"}

        if stocks_building and rich_margins:
            return (
                "watch",
                "Inventories are building while crush margins stay strong.",
            )
        if production_elevated and soft_margins:
            return (
                "watch",
                "Production is elevated while crush margins look soft.",
            )
        if stocks_building:
            return (
                "watch",
                "Ethanol stocks are building versus the prior four weeks.",
            )

        return (
            "calm",
            "No inventory or production stress signals for the latest session.",
        )

    @staticmethod
    def _empty_snapshot() -> dict:
        """Return a blank snapshot when merged history is missing."""
        return {
            "stocks_mmbbl": None,
            "stocks_change_28d_pct": None,
            "production_mbpd": None,
            "production_vs_180d_avg_pct": None,
            "margin_signal_label": None,
            "status": "calm",
            "status_message": "No merged market history available yet.",
        }
