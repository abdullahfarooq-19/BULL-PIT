"""NYSE sessions and closes, offline (dev-plan.md D2).

Every date-vs-cutoff decision in the data layer (bullpit/data/guard.py)
depends on this module knowing exactly which dates are sessions and when
each one's close is, including early closes and DST. `bullpit/clock.py`
is the only other module allowed to know "now"; everything here is pure
given a date or a moment.
"""

from __future__ import annotations

import bisect
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

from bullpit.errors import ConfigError

_CALENDAR_START = "2000-01-01"
_CALENDAR_END = "2035-12-31"

NEW_YORK = ZoneInfo("America/New_York")


@lru_cache(maxsize=1)
def _schedule() -> pd.DataFrame:
    """NYSE sessions and their UTC closes for the supported date range.

    Indexed by session date; one column `close` (UTC, tz-aware).
    """
    calendar = mcal.get_calendar("XNYS")
    sched = calendar.schedule(start_date=_CALENDAR_START, end_date=_CALENDAR_END)
    return pd.DataFrame({"close": sched["market_close"]}, index=sched.index.date)


def is_session(day: date) -> bool:
    return day in _schedule().index


def session_close(day: date) -> datetime:
    """The UTC datetime of `day`'s close: the knowledge cutoff for that session."""
    schedule = _schedule()
    if day not in schedule.index:
        raise ConfigError(f"{day} is not an NYSE session")
    close = cast(pd.Timestamp, schedule.at[day, "close"])
    return close.to_pydatetime()


def last_completed_session(moment: datetime) -> date:
    """The most recent session whose close is on or before `moment`.

    Pure; `LiveClock` passes the wall clock. `moment` must be timezone-aware.
    """
    if moment.tzinfo is None:
        raise ConfigError("last_completed_session requires a timezone-aware moment")
    schedule = _schedule()
    closes = schedule["close"]
    if moment < closes.iloc[0]:
        raise ConfigError(f"{moment} is before the supported calendar range")
    index = bisect.bisect_right(closes.to_list(), moment) - 1
    return cast(date, closes.index[index])


def sessions_between(after: date, through: date) -> list[date]:
    """The sessions in `(after, through]`, oldest first. Dates need not be sessions."""
    return [day for day in _schedule().index if after < day <= through]


def decision_days(start: date, weeks: int) -> list[date]:
    """The last session of each of `weeks` calendar weeks (Monday to Sunday),
    beginning with the week that contains `start` and using only sessions on
    or after `start` (M6-FR-8). A week with no such session is skipped.
    """
    monday = start - timedelta(days=start.weekday())
    days: list[date] = []
    for week in range(weeks):
        week_start = monday + timedelta(weeks=week)
        first = max(start, week_start)
        sessions = sessions_between(first - timedelta(days=1), week_start + timedelta(days=6))
        if sessions:
            days.append(sessions[-1])
    return days


def lookback_start(as_of: date, sessions: int) -> date:
    """The first session of an `sessions`-session lookback ending at `as_of`."""
    schedule = _schedule()
    if as_of not in schedule.index:
        raise ConfigError(f"{as_of} is not an NYSE session")
    position = cast(int, schedule.index.get_loc(as_of))
    start_position = position - (sessions - 1)
    if start_position < 0:
        raise ConfigError(
            f"lookback of {sessions} sessions ending {as_of} starts before the "
            "supported calendar range"
        )
    return cast(date, schedule.index[start_position])
