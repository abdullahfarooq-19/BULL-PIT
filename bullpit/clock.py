"""The system's one source of "now" (dev-plan.md D5, M0-FR-3).

Every other module gets the current moment through an injected `Clock`;
this is the only file allowed to read the wall clock (ruff's TID251 ban
on `datetime.now`/`date.today` is exempted here, in pyproject.toml).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol

from bullpit.data.calendar import is_session, last_completed_session
from bullpit.errors import ConfigError


def utc_now() -> datetime:
    """The current UTC moment. Never call `datetime.now()` elsewhere."""
    return datetime.now(UTC)


class Clock(Protocol):
    def as_of(self) -> date:
        """The date to treat as "today" for this request."""
        ...


class LiveClock:
    """`as_of` is the latest NYSE session whose close has already happened."""

    def as_of(self) -> date:
        return last_completed_session(utc_now())


class SimClock:
    """`as_of` is a fixed date, for backtests."""

    def __init__(self, as_of: date) -> None:
        if not is_session(as_of):
            raise ConfigError(f"SimClock as_of is not an NYSE session: {as_of}")
        self._as_of = as_of

    def as_of(self) -> date:
        return self._as_of
