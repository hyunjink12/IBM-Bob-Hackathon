"""Upcoming scheduled data releases (EIA / WASDE / CFTC COT)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ScheduledRelease:
    """
    One upcoming publisher event.

    Casual: which agency prints what, when, and how far away.

    `released_at_et` is stored as an ISO string in Eastern time — the tape
    surfaces both a countdown ("in 3d") and the raw stamp for hover context.
    """

    source: str  # "EIA" | "USDA WASDE" | "CFTC COT"
    label: str
    released_at_et: datetime
    days_until: int
    hours_until: int
    is_approximate: bool = False

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "label": self.label,
            "released_at_et": self.released_at_et.isoformat(),
            "days_until": self.days_until,
            "hours_until": self.hours_until,
            "is_approximate": self.is_approximate,
        }


class ReleaseScheduleManager:
    """
    Compute next release times for the recurring agency reports.

    Casual: 'when is the next EIA / WASDE / COT?' in one place.

    EIA WPSR — Wednesday 10:30 AM ET (Thursday on federal-holiday weeks; not
    modeled here). CFTC COT — Friday 3:30 PM ET (same holiday shift caveat).

    WASDE — read from `config/wasde_schedule.json` (source-of-truth: USDA
    published calendar). When the requested month is not in the file, we fall
    back to the "second Tuesday of the month at 12:00 ET" approximation and
    flag the returned release with `is_approximate=True` so the UI can badge it.
    """

    EIA_WEEKDAY = 2  # Wednesday
    EIA_TIME = time(10, 30)

    COT_WEEKDAY = 4  # Friday
    COT_TIME = time(15, 30)

    WASDE_TIME = time(12, 0)

    def __init__(self, wasde_schedule_path: Path | None = None) -> None:
        self._wasde_dates = self._load_wasde_schedule(wasde_schedule_path)

    def next_eia_release(self, now: datetime | None = None) -> ScheduledRelease:
        now_et = _now_et(now)
        released = _next_weekday_at(now_et, self.EIA_WEEKDAY, self.EIA_TIME)
        return _build_release("EIA", "EIA Weekly Petroleum Status", released, now_et)

    def next_cot_release(self, now: datetime | None = None) -> ScheduledRelease:
        now_et = _now_et(now)
        released = _next_weekday_at(now_et, self.COT_WEEKDAY, self.COT_TIME)
        return _build_release("CFTC COT", "CFTC Commitments of Traders", released, now_et)

    def next_wasde_release(self, now: datetime | None = None) -> ScheduledRelease:
        """Prefer USDA-published date; approximate only when the file has no entry."""
        now_et = _now_et(now)
        official = self._next_official_wasde(now_et)
        if official is not None:
            return _build_release("USDA WASDE", "USDA WASDE", official, now_et)
        approximated = self._approximate_next_wasde(now_et)
        return _build_release(
            "USDA WASDE",
            "USDA WASDE (approximate)",
            approximated,
            now_et,
            is_approximate=True,
        )

    def upcoming_releases(self, now: datetime | None = None) -> list[ScheduledRelease]:
        return [
            self.next_eia_release(now),
            self.next_wasde_release(now),
            self.next_cot_release(now),
        ]

    def _next_official_wasde(self, now_et: datetime) -> datetime | None:
        for candidate in self._wasde_dates:
            if candidate > now_et:
                return candidate
        return None

    def _approximate_next_wasde(self, now_et: datetime) -> datetime:
        candidate = _second_tuesday(now_et.year, now_et.month)
        released = datetime.combine(candidate, self.WASDE_TIME, tzinfo=ET)
        if released <= now_et:
            next_month = now_et.month + 1
            next_year = now_et.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            candidate = _second_tuesday(next_year, next_month)
            released = datetime.combine(candidate, self.WASDE_TIME, tzinfo=ET)
        return released

    @staticmethod
    def _load_wasde_schedule(path: Path | None) -> list[datetime]:
        """
        Read published WASDE dates into a sorted list of ET datetimes.

        Missing file → empty list → every WASDE call falls back to approximation.
        Malformed rows are skipped rather than raising, so an old file with a
        stray typo can't crash the whole tape endpoint.
        """
        if path is None:
            repo_root = Path(__file__).resolve().parents[3]
            path = repo_root / "config" / "wasde_schedule.json"
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        release_time_str = payload.get("release_time_et", "12:00")
        try:
            hour_str, minute_str = release_time_str.split(":")
            release_time = time(int(hour_str), int(minute_str))
        except (ValueError, AttributeError):
            release_time = time(12, 0)

        dates: list[datetime] = []
        for raw in payload.get("dates", []):
            try:
                obs = date.fromisoformat(str(raw))
            except (TypeError, ValueError):
                continue
            dates.append(datetime.combine(obs, release_time, tzinfo=ET))
        dates.sort()
        return dates


def _now_et(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(tz=ET)
    return now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=ET)


def _next_weekday_at(now_et: datetime, weekday: int, at: time) -> datetime:
    """Next occurrence of `weekday` (Mon=0..Sun=6) at `at` (ET), strictly after now."""
    days_ahead = (weekday - now_et.weekday()) % 7
    candidate = datetime.combine(now_et.date() + timedelta(days=days_ahead), at, tzinfo=ET)
    if candidate <= now_et:
        candidate += timedelta(days=7)
    return candidate


def _second_tuesday(year: int, month: int) -> date:
    """Second Tuesday of the given month — WASDE-week approximation."""
    first = date(year, month, 1)
    first_tuesday = first + timedelta(days=(1 - first.weekday()) % 7)
    return first_tuesday + timedelta(days=7)


def _build_release(
    source: str,
    label: str,
    released_at_et: datetime,
    now_et: datetime,
    is_approximate: bool = False,
) -> ScheduledRelease:
    delta = released_at_et - now_et
    total_hours = int(delta.total_seconds() // 3600)
    return ScheduledRelease(
        source=source,
        label=label,
        released_at_et=released_at_et,
        days_until=delta.days,
        hours_until=total_hours,
        is_approximate=is_approximate,
    )
