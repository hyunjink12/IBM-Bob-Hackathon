"""Rolling and expanding z-score calculations for crush margins."""

from __future__ import annotations

from datetime import date, timedelta

from app.managers.signal_label_manager import SignalLabelManager


class ZScoreManager:
    """
    Computes z-scores over a lookback window on margin history.

    Casual: how weird is today's margin vs the last few years?

    Supports rolling windows (default 5Y) and expanding windows from the
    first observation. Uses population std (ddof=0) for stable trading stats.
    """

    def __init__(self, signal_label_manager: SignalLabelManager | None = None) -> None:
        self._signal_label_manager = signal_label_manager or SignalLabelManager()

    def annotate_series(
        self,
        margin_points: list[tuple[date, float]],
        *,
        window_type: str = "rolling",
        lookback_days: int = 1825,
    ) -> list[tuple[date, float, float | None, str]]:
        """
        Return (date, margin, z_score, signal_label) for each point.

        z_score is None until the window has at least two observations.
        """
        if not margin_points:
            return []

        sorted_points = sorted(margin_points, key=lambda item: item[0])
        results: list[tuple[date, float, float | None, str]] = []

        for index, (obs_date, margin) in enumerate(sorted_points):
            window_values = self._window_values(
                sorted_points,
                index=index,
                window_type=window_type,
                lookback_days=lookback_days,
            )
            z_score = self._z_score(margin, window_values)
            label = (
                self._signal_label_manager.label_for_z_score(z_score)
                if z_score is not None
                else "normal"
            )
            results.append((obs_date, margin, z_score, label))

        return results

    def _window_values(
        self,
        sorted_points: list[tuple[date, float]],
        *,
        index: int,
        window_type: str,
        lookback_days: int,
    ) -> list[float]:
        obs_date = sorted_points[index][0]
        if window_type == "expanding":
            return [value for _, value in sorted_points[: index + 1]]

        cutoff = obs_date - timedelta(days=lookback_days)
        return [
            value
            for point_date, value in sorted_points[: index + 1]
            if point_date >= cutoff
        ]

    @staticmethod
    def _z_score(value: float, window_values: list[float]) -> float | None:
        if len(window_values) < 2:
            return None
        mean_value = sum(window_values) / len(window_values)
        variance = sum((item - mean_value) ** 2 for item in window_values) / len(
            window_values
        )
        if variance == 0:
            return 0.0
        std_dev = variance**0.5
        return (value - mean_value) / std_dev

    @staticmethod
    def parse_range_to_days(range_token: str) -> int | None:
        """Convert API range tokens like 1Y into day counts; All returns None."""
        mapping = {"1Y": 365, "2Y": 730, "5Y": 1825}
        if range_token.upper() == "ALL":
            return None
        return mapping.get(range_token.upper(), 365)
