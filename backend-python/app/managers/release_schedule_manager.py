"""Upcoming scheduled data releases (EIA / WASDE / CFTC COT)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "label": self.label,
            "released_at_et": self.released_at_et.isoformat(),
            "days_until": self.days_until,
            "hours_until": self.hours_until,
        }


class ReleaseScheduleManager:
    """
    Compute next release times for the recurring agency reports.

    Casual: 'when is the next EIA / WASDE / COT?' in one place.

    EIA WPSR — Wednesday 10:30 AM ET (Thursday on federal-holiday weeks; not
    modeled here). CFTC COT — Friday 3:30 PM ET (same holiday shift caveat).
    WASDE — monthly, ~2nd week around the 10th at 12:00 PM ET; approximated
    as the second Tuesday of the month. For production accuracy, replace the
    WASDE rule with the published USDA calendar table.
    """

    EIA_WEEKDAY = 2  # Wednesday
    EIA_TIME = time(10, 30)

    COT_WEEKDAY = 4  # Friday
    COT_TIME = time(15, 30)

    WASDE_TIME = time(12, 0)

    def next_eia_release(self, now: datetime | None = None) -> ScheduledRelease:
        now_et = _now_et(now)
        released = _next_weekday_at(now_et, self.EIA_WEEKDAY, self.EIA_TIME)
        return _build_release("EIA", "EIA Weekly Petroleum Status", released, now_et)

    def next_cot_release(self, now: datetime | None = None) -> ScheduledRelease:
        now_et = _now_et(now)
        released = _next_weekday_at(now_et, self.COT_WEEKDAY, self.COT_TIME)
        return _build_release("CFTC COT", "CFTC Commitments of Traders", released, now_et)

    def next_wasde_release(self, now: datetime | None = None) -> ScheduledRelease:
        now_et = _now_et(now)
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
        return _build_release("USDA WASDE", "USDA WASDE", released, now_et)

    def upcoming_releases(self, now: datetime | None = None) -> list[ScheduledRelease]:
        return [
            self.next_eia_release(now),
            self.next_wasde_release(now),
            self.next_cot_release(now),
        ]


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
) -> ScheduledRelease:
    delta = released_at_et - now_et
    total_hours = int(delta.total_seconds() // 3600)
    return ScheduledRelease(
        source=source,
        label=label,
        released_at_et=released_at_et,
        days_until=delta.days,
        hours_until=total_hours,
    )
