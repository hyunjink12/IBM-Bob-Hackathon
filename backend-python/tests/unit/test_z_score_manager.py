"""Unit tests for z-score manager."""

from datetime import date, timedelta

import pytest

from app.managers.z_score_manager import ZScoreManager


@pytest.mark.unit
def test_z_score_labels_follow_thresholds() -> None:
    manager = ZScoreManager()
    annotated = manager.annotate_series(
        [
            (date(2024, 1, 1), 0.0),
            (date(2024, 1, 2), 0.0),
            (date(2024, 1, 3), 0.0),
            (date(2024, 1, 4), 100.0),
        ],
        window_type="expanding",
    )
    assert annotated[-1][3] == "rich"


@pytest.mark.unit
def test_parse_range_to_days() -> None:
    manager = ZScoreManager()
    assert manager.parse_range_to_days("5Y") == 1825
    assert manager.parse_range_to_days("ALL") is None


@pytest.mark.unit
def test_rolling_window_limits_history() -> None:
    manager = ZScoreManager()
    start = date(2020, 1, 1)
    points = [(start + timedelta(days=index), float(index)) for index in range(400)]
    annotated = manager.annotate_series(points, lookback_days=30)
    assert len(annotated) == 400
    assert annotated[-1][2] is not None
