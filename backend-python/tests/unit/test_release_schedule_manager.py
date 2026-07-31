"""Unit tests for ReleaseScheduleManager countdown calculations."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.managers.release_schedule_manager import ReleaseScheduleManager


ET = ZoneInfo("America/New_York")


@pytest.mark.unit
def test_eia_release_lands_on_next_wednesday_1030() -> None:
    manager = ReleaseScheduleManager()
    # A Monday at 9am ET → next EIA is Wednesday same week at 10:30 ET.
    now = datetime(2026, 7, 27, 9, 0, tzinfo=ET)
    release = manager.next_eia_release(now)
    assert release.released_at_et.weekday() == 2  # Wednesday
    assert release.released_at_et.hour == 10
    assert release.released_at_et.minute == 30
    assert release.days_until == 2


@pytest.mark.unit
def test_eia_release_rolls_when_current_wednesday_already_published() -> None:
    manager = ReleaseScheduleManager()
    # Wednesday 11am ET (past 10:30 release) → next EIA is following week.
    now = datetime(2026, 7, 29, 11, 0, tzinfo=ET)
    release = manager.next_eia_release(now)
    assert release.released_at_et.weekday() == 2
    assert (release.released_at_et.date() - now.date()).days == 7


@pytest.mark.unit
def test_cot_release_is_next_friday_1530() -> None:
    manager = ReleaseScheduleManager()
    now = datetime(2026, 7, 27, 9, 0, tzinfo=ET)  # Mon
    release = manager.next_cot_release(now)
    assert release.released_at_et.weekday() == 4  # Friday
    assert release.released_at_et.hour == 15
    assert release.released_at_et.minute == 30


@pytest.mark.unit
def test_wasde_release_uses_second_tuesday_approximation() -> None:
    manager = ReleaseScheduleManager()
    # Early August → next WASDE is second Tuesday of August 2026 = Aug 11.
    now = datetime(2026, 8, 3, 9, 0, tzinfo=ET)
    release = manager.next_wasde_release(now)
    assert release.released_at_et.year == 2026
    assert release.released_at_et.month == 8
    assert release.released_at_et.day == 11  # 2nd Tuesday of Aug 2026
    assert release.released_at_et.hour == 12


@pytest.mark.unit
def test_wasde_rolls_to_next_month_when_second_tuesday_already_passed() -> None:
    manager = ReleaseScheduleManager()
    now = datetime(2026, 8, 20, 9, 0, tzinfo=ET)  # after Aug 11 WASDE
    release = manager.next_wasde_release(now)
    assert release.released_at_et.month == 9
    assert release.released_at_et.day == 8  # 2nd Tuesday of Sep 2026
