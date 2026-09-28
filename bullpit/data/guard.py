"""The response check every data tool's result passes through (dev-plan.md
Part 2; architecture.md sec11). Runs after every fetch and after every
cache read (M1-FR-6), so a cache hit can never skip it.

The `as_of` limit is decided by the column's dtype, not a per-call flag
(M1-FR-4): a timezone-aware column (news `created_at`) is compared with
the session close; a naive date column (bar date, SEC `filed`) is
compared with `as_of` itself.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from bullpit.data.calendar import session_close
from bullpit.errors import LookaheadViolation
from bullpit.logging import get_logger

logger = get_logger(__name__)


def drop_after(
    frame: pd.DataFrame,
    column: str,
    as_of: date,
    *,
    later_rows_expected: bool,
    dataset: str,
    symbol: str,
) -> pd.DataFrame:
    """Drop every row dated after `as_of`'s knowledge cutoff.

    `later_rows_expected` sets the log level for a dropped row: a warning
    when a source ignored the request filter, debug when it's expected
    (a cache read, or SEC, which has no request filter). A row with no
    usable date can't be proven safe, so it raises `LookaheadViolation`
    instead of being dropped (M1-FR-7).
    """
    if frame.empty:
        return frame
    column_values = frame[column]
    if not is_datetime64_any_dtype(column_values):
        raise LookaheadViolation(
            f"{dataset}/{symbol}: column {column!r} is not a datetime column, can't prove it's safe"
        )
    if column_values.isna().any():
        raise LookaheadViolation(
            f"{dataset}/{symbol}: column {column!r} has an undated row, can't prove it's safe"
        )
    limit = (
        pd.Timestamp(session_close(as_of))
        if isinstance(column_values.dtype, pd.DatetimeTZDtype)
        else pd.Timestamp(as_of)
    )
    keep = column_values <= limit
    if bool(keep.all()):
        return frame

    log = logger.debug if later_rows_expected else logger.warning
    for row_date in frame.loc[~keep, column]:
        log(
            "lookahead_row_dropped",
            dataset=dataset,
            symbol=symbol,
            row_date=str(row_date),
            as_of=str(as_of),
        )
    return frame.loc[keep]
