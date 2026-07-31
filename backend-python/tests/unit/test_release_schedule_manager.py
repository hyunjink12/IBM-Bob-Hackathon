"""Unit tests for ReleaseScheduleManager countdown calculations."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.managers.release_schedule_manager import ReleaseScheduleManager


ET = ZoneInfo("America/New_York")


@pytest.fixture
def empty_schedule_manager(tmp_path: Path) -> ReleaseScheduleManager:
    """Manager with no WASDE calendar file → always uses approximation."""
    missing_path = tmp_path / "no-such-file.json"
    return ReleaseScheduleManager(wasde_schedule_path=missing_path)


@pytest.fixture
def official_schedule_manager(tmp_path: Path) -> ReleaseScheduleManager:
    """Manager loaded with a small hand-crafted WASDE calendar."""
    schedule_path = tmp_path / "wasde.json"
    schedule_path.write_text(
        json.dumps(
            {
                "release_time_et": "12:00",
                "dates": ["2026-08-12", "2026-09-11", "2026-10-09"],
            }
        )
    )
    return ReleaseScheduleManager(wasde_schedule_path=schedule_path)


@pytest.mark.unit
def test_eia_release_lands_on_next_wednesday_1030(empty_schedule_manager) -> None:
    now = datetime(2026, 7, 27, 9, 0, tzinfo=ET)  # Mon 9am ET
    release = empty_schedule_manager.next_eia_release(now)
    assert release.released_at_et.weekday() == 2  # Wednesday
    assert release.released_at_et.hour == 10
    assert release.released_at_et.minute == 30
    assert release.days_until == 2


@pytest.mark.unit
def test_eia_release_rolls_when_current_wednesday_already_published(empty_schedule_manager) -> None:
    now = datetime(2026, 7, 29, 11, 0, tzinfo=ET)  # Wed 11am ET, past 10:30
    release = empty_schedule_manager.next_eia_release(now)
    assert release.released_at_et.weekday() == 2
    assert (release.released_at_et.date() - now.date()).days == 7


@pytest.mark.unit
def test_cot_release_is_next_friday_1530(empty_schedule_manager) -> None:
    now = datetime(2026, 7, 27, 9, 0, tzinfo=ET)  # Mon
    release = empty_schedule_manager.next_cot_release(now)
    assert release.released_at_et.weekday() == 4  # Friday
    assert release.released_at_et.hour == 15
    assert release.released_at_et.minute == 30


@pytest.mark.unit
def test_wasde_uses_official_calendar_when_available(official_schedule_manager) -> None:
    """When the USDA-published date is in the file, it wins over the approximation."""
    now = datetime(2026, 8, 3, 9, 0, tzinfo=ET)
    release = official_schedule_manager.next_wasde_release(now)
    assert release.released_at_et.date().isoformat() == "2026-08-12"
    assert release.released_at_et.hour == 12
    assert release.is_approximate is False


@pytest.mark.unit
def test_wasde_falls_back_to_approximation_when_file_missing(empty_schedule_manager) -> None:
    """No calendar file → second-Tuesday guess, flagged as approximate."""
    now = datetime(2026, 8, 3, 9, 0, tzinfo=ET)
    release = empty_schedule_manager.next_wasde_release(now)
    assert release.released_at_et.day == 11  # second Tuesday of Aug 2026
    assert release.is_approximate is True


@pytest.mark.unit
def test_wasde_falls_back_when_file_has_no_future_dates(official_schedule_manager) -> None:
    """After the last date in the file, the manager approximates again."""
    now = datetime(2027, 6, 1, 9, 0, tzinfo=ET)  # past every date in the fixture
    release = official_schedule_manager.next_wasde_release(now)
    assert release.is_approximate is True
