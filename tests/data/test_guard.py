"""The date guard (M1-FR-4 to FR-7).

`test_drop_after` is the unit half of M1-AC-2. The cross-tool leak tests
(AC-1, the rest of AC-2) are added by M1-T-9.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from structlog.testing import capture_logs

from bullpit.data.guard import drop_after
from bullpit.errors import LookaheadViolation


def _date_frame(dates: list[date]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(dates)})


class TestDropAfter:
    def test_later_row_is_dropped_and_logged_as_warning(self) -> None:
        frame = _date_frame([date(2024, 6, 5), date(2024, 6, 7), date(2024, 6, 10)])
        with capture_logs() as logs:
            result = drop_after(
                frame,
                "date",
                date(2024, 6, 7),
                later_rows_expected=False,
                dataset="prices",
                symbol="AAPL",
            )

        assert len(result) == 2
        assert result["date"].max() == pd.Timestamp(date(2024, 6, 7))
        dropped = [log for log in logs if log["event"] == "lookahead_row_dropped"]
        assert len(dropped) == 1
        assert dropped[0]["log_level"] == "warning"
        assert dropped[0]["dataset"] == "prices"
        assert dropped[0]["symbol"] == "AAPL"
        assert dropped[0]["as_of"] == "2024-06-07"

    def test_expected_later_row_is_logged_at_debug(self) -> None:
        frame = _date_frame([date(2024, 6, 10)])
        with capture_logs() as logs:
            result = drop_after(
                frame,
                "date",
                date(2024, 6, 7),
                later_rows_expected=True,
                dataset="sec_facts",
                symbol="AAPL",
            )

        assert len(result) == 0
        dropped = [log for log in logs if log["event"] == "lookahead_row_dropped"]
        assert dropped[0]["log_level"] == "debug"

    def test_no_rows_dropped_when_nothing_is_later(self) -> None:
        frame = _date_frame([date(2024, 6, 5), date(2024, 6, 7)])
        result = drop_after(
            frame, "date", date(2024, 6, 7), later_rows_expected=False, dataset="p", symbol="A"
        )
        assert len(result) == 2

    def test_undated_row_raises_lookahead_violation(self) -> None:
        frame = pd.DataFrame({"date": pd.to_datetime([date(2024, 6, 5), None])})
        with pytest.raises(LookaheadViolation):
            drop_after(
                frame, "date", date(2024, 6, 7), later_rows_expected=False, dataset="p", symbol="A"
            )

    def test_non_datetime_column_raises_lookahead_violation(self) -> None:
        frame = pd.DataFrame({"date": ["2024-06-05", "2024-06-07"]})
        with pytest.raises(LookaheadViolation):
            drop_after(
                frame, "date", date(2024, 6, 7), later_rows_expected=False, dataset="p", symbol="A"
            )
