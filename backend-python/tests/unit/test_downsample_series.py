"""Unit tests for the chart granularity downsampling helper."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.managers.dashboard_manager import _downsample_series


def _daily_series(start: date, days: int) -> list[dict]:
    return [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            "margin_per_bushel": 1.0 + i * 0.01,
        }
        for i in range(days)
    ]


@pytest.mark.unit
def test_daily_is_passthrough() -> None:
    series = _daily_series(date(2026, 1, 1), 30)
    assert _downsample_series(series, "daily") is series


@pytest.mark.unit
def test_empty_series_is_passthrough() -> None:
    assert _downsample_series([], "weekly") == []
    assert _downsample_series([], "monthly") == []


@pytest.mark.unit
def test_unknown_granularity_returns_input_unchanged() -> None:
    """Bad `granularity` values should not silently drop data — pass through."""
    series = _daily_series(date(2026, 1, 1), 10)
    assert _downsample_series(series, "quarterly") == series


@pytest.mark.unit
def test_weekly_keeps_one_row_per_iso_week() -> None:
    """
    28 consecutive days spans 5 ISO weeks. Weekly downsample should yield 5 rows,
    and each should be the last observed date in its ISO week.
    """
    series = _daily_series(date(2026, 1, 1), 28)  # Thu 2026-01-01 → Wed 2026-01-28
    result = _downsample_series(series, "weekly")
    assert len(result) == 5
    # Each result row is the last date in its ISO week — verify each has a
    # later date than the row before it and is unique.
    dates = [row["date"] for row in result]
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


@pytest.mark.unit
def test_weekly_keeps_last_obs_of_period_not_average() -> None:
    """Downsampling picks the last row, not an average — margin values match daily."""
    series = _daily_series(date(2026, 1, 5), 14)  # Mon → Sun (2 full ISO weeks)
    result = _downsample_series(series, "weekly")
    assert len(result) == 2
    # Every downsampled row's margin value should exist verbatim in the daily source.
    daily_values_by_date = {row["date"]: row["margin_per_bushel"] for row in series}
    for row in result:
        assert row["margin_per_bushel"] == daily_values_by_date[row["date"]]


@pytest.mark.unit
def test_monthly_keeps_one_row_per_calendar_month() -> None:
    """150 days from Jan 1 spans 5 calendar months (Jan–May)."""
    series = _daily_series(date(2026, 1, 1), 150)
    result = _downsample_series(series, "monthly")
    assert len(result) == 5
    months = [row["date"][:7] for row in result]  # YYYY-MM
    assert months == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]


@pytest.mark.unit
def test_monthly_last_row_of_each_month_matches_source() -> None:
    """Each monthly row must be the actual last-observed daily row of that month."""
    series = _daily_series(date(2026, 3, 20), 25)  # Mar 20 → Apr 13
    result = _downsample_series(series, "monthly")
    # The last row for March in the source is 2026-03-31.
    march = next(r for r in result if r["date"].startswith("2026-03"))
    assert march["date"] == "2026-03-31"
    # The last row for April is 2026-04-13 (the source's tip).
    april = next(r for r in result if r["date"].startswith("2026-04"))
    assert april["date"] == "2026-04-13"


@pytest.mark.unit
def test_carries_all_row_fields_through() -> None:
    """Downsampling must not drop z_score / signal_label / other keys."""
    series = [
        {
            "date": "2026-01-05",
            "margin_per_bushel": 1.0,
            "z_score": 0.5,
            "signal_label": "normal",
        },
        {
            "date": "2026-01-09",
            "margin_per_bushel": 1.1,
            "z_score": 0.6,
            "signal_label": "normal",
        },
    ]
    result = _downsample_series(series, "weekly")
    assert len(result) == 1
    # Both are in ISO week 2 of 2026, so we keep the later row and its full payload.
    assert result[0] == series[-1]
