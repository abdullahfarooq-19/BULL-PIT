"""The calendar the date guard depends on (M1-AC-6).

Known dates checked against pandas-market-calendars 5.4.0 on 2026-09-28
(plan.md sec3.2): weekends and holidays closed, early closes at the right
UTC hour either side of DST, and last_completed_session at a close boundary.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from bullpit.data.calendar import (
    is_session,
    last_completed_session,
    lookback_start,
    session_close,
)
from bullpit.errors import ConfigError

NOT_SESSIONS = [
    pytest.param(date(2024, 3, 9), id="saturday"),
    pytest.param(date(2024, 3, 10), id="sunday"),
    pytest.param(date(2024, 3, 29), id="good-friday-2024"),
    pytest.param(date(2024, 11, 28), id="thanksgiving-2024"),
]

EARLY_CLOSES = [
    pytest.param(date(2024, 7, 3), datetime(2024, 7, 3, 17, 0, tzinfo=UTC), id="jul-3-2024"),
    pytest.param(date(2024, 11, 29), datetime(2024, 11, 29, 18, 0, tzinfo=UTC), id="nov-29-2024"),
]

NORMAL_CLOSES_ACROSS_DST = [
    pytest.param(date(2024, 3, 8), datetime(2024, 3, 8, 21, 0, tzinfo=UTC), id="before-dst"),
    pytest.param(date(2024, 3, 11), datetime(2024, 3, 11, 20, 0, tzinfo=UTC), id="after-dst"),
]


class TestIsSession:
    @pytest.mark.parametrize("day", NOT_SESSIONS)
    def test_not_a_session(self, day: date) -> None:
        assert is_session(day) is False

    def test_a_normal_weekday_is_a_session(self) -> None:
        assert is_session(date(2024, 6, 7)) is True


class TestSessionClose:
    @pytest.mark.parametrize(("day", "expected"), EARLY_CLOSES)
    def test_early_close(self, day: date, expected: datetime) -> None:
        assert session_close(day) == expected

    @pytest.mark.parametrize(("day", "expected"), NORMAL_CLOSES_ACROSS_DST)
    def test_normal_close_across_dst(self, day: date, expected: datetime) -> None:
        assert session_close(day) == expected

    @pytest.mark.parametrize("day", NOT_SESSIONS)
    def test_raises_for_non_session(self, day: date) -> None:
        with pytest.raises(ConfigError):
            session_close(day)


class TestLastCompletedSession:
    def test_just_before_a_close(self) -> None:
        moment = datetime(2024, 6, 7, 19, 59, tzinfo=UTC)
        assert last_completed_session(moment) == date(2024, 6, 6)

    def test_just_after_a_close(self) -> None:
        moment = datetime(2024, 6, 7, 20, 1, tzinfo=UTC)
        assert last_completed_session(moment) == date(2024, 6, 7)

    def test_requires_timezone_aware_moment(self) -> None:
        with pytest.raises(ConfigError):
            last_completed_session(datetime(2024, 6, 7, 20, 1))  # noqa: DTZ001


class TestLookbackStart:
    def test_one_session_is_as_of_itself(self) -> None:
        assert lookback_start(date(2024, 6, 7), 1) == date(2024, 6, 7)

    def test_multi_session_window(self) -> None:
        # 2024-06-07 is a Friday; the prior 4 sessions are Mon-Thu that week.
        assert lookback_start(date(2024, 6, 7), 5) == date(2024, 6, 3)

    def test_raises_if_as_of_not_a_session(self) -> None:
        with pytest.raises(ConfigError):
            lookback_start(date(2024, 3, 9), 5)
