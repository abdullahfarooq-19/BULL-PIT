"""Parquet cache, re-checked by the guard on every read (dev-plan.md Part 2).

Each dataset/symbol has one entry that grows as a continuous window
(plan.md P-2), so a backtest fetches each new day once and a resumed or
repeated run reads identical data from disk. `read_through` is the one
place every tool's cache path runs both guard passes (plan.md P-1): the
fetched pieces are checked before they're merged in, and the merged
result is checked again before it's returned, so a cache hit can never
skip the guard.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast
from urllib.parse import quote

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from bullpit.clock import utc_now
from bullpit.config import Settings
from bullpit.data.calendar import NEW_YORK, last_completed_session
from bullpit.data.guard import drop_after
from bullpit.logging import get_logger

logger = get_logger(__name__)

_START_KEY = b"bullpit_start"
_COMPLETE_THROUGH_KEY = b"bullpit_complete_through"


@dataclass(frozen=True)
class CacheEntry:
    frame: pd.DataFrame
    start: date
    complete_through: date


def _path(dataset: str, symbol: str, *, settings: Settings) -> Path:
    return settings.data_cache_dir / dataset / f"{quote(symbol, safe='')}.parquet"


def load(dataset: str, symbol: str, *, settings: Settings) -> CacheEntry | None:
    path = _path(dataset, symbol, settings=settings)
    if not path.exists():
        return None
    table = pq.read_table(path)
    metadata = table.schema.metadata or {}
    entry = CacheEntry(
        frame=table.to_pandas(),
        start=date.fromisoformat(metadata[_START_KEY].decode()),
        complete_through=date.fromisoformat(metadata[_COMPLETE_THROUGH_KEY].decode()),
    )
    return entry


def save(dataset: str, symbol: str, entry: CacheEntry, *, settings: Settings) -> None:
    path = _path(dataset, symbol, settings=settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(entry.frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[_START_KEY] = entry.start.isoformat().encode()
    metadata[_COMPLETE_THROUGH_KEY] = entry.complete_through.isoformat().encode()
    table = table.replace_schema_metadata(metadata)
    tmp_path = path.with_suffix(".tmp")
    pq.write_table(table, tmp_path)
    tmp_path.replace(path)


def complete_through(end: date, fetched_at: datetime) -> date:
    """The date a fetch made at `fetched_at` can be trusted complete through.

    Data fetched on a later New York date than `end` is complete through
    `end`; a same-day fetch is complete only through the session before
    (M1-FR-16, D-M1-4): a same-day fetch may still be missing that day's
    late filings or news.
    """
    midnight_ny = datetime.combine(fetched_at.astimezone(NEW_YORK).date(), datetime.min.time())
    limit = last_completed_session(midnight_ny.replace(tzinfo=NEW_YORK))
    return min(end, limit)


def missing_ranges(entry: CacheEntry | None, start: date, as_of: date) -> list[tuple[date, date]]:
    """The date ranges not already covered by `entry` (M1-FR-16).

    No entry, or a request ending before the entry starts, needs the
    whole window fetched (and the entry replaced, not merged): merging
    there would mean fetching past `as_of` or recording a gap as covered.
    """
    if entry is None or as_of < entry.start:
        return [(start, as_of)]
    ranges: list[tuple[date, date]] = []
    if start < entry.start:
        ranges.append((start, entry.start))
    if as_of > entry.complete_through:
        ranges.append((entry.complete_through, as_of))
    return ranges


def read_through(
    dataset: str,
    symbol: str,
    start: date,
    as_of: date,
    *,
    fetch: Callable[[date, date], pd.DataFrame],
    key: list[str],
    date_column: str,
    settings: Settings,
) -> pd.DataFrame:
    entry = load(dataset, symbol, settings=settings)
    ranges = missing_ranges(entry, start, as_of)

    if not ranges:
        # missing_ranges only returns [] when a covering entry exists.
        covering = cast(CacheEntry, entry)
        logger.info("cache_hit", dataset=dataset, symbol=symbol, start=str(start), as_of=str(as_of))
        result = covering.frame
    else:
        logger.info(
            "cache_miss",
            dataset=dataset,
            symbol=symbol,
            ranges=[(str(a), str(b)) for a, b in ranges],
        )
        pieces = [
            drop_after(
                fetch(a, b),
                date_column,
                as_of,
                later_rows_expected=False,
                dataset=dataset,
                symbol=symbol,
            )
            for a, b in ranges
        ]
        fetched_at = utc_now()
        replace = entry is None or as_of < entry.start
        base = [] if replace or entry is None else [entry.frame]
        merged = pd.concat([*base, *pieces], ignore_index=True)
        merged = merged.drop_duplicates(subset=key, keep="last").sort_values(date_column)
        new_start = start if replace or entry is None else min(start, entry.start)
        new_complete_through = (
            complete_through(as_of, fetched_at)
            if replace or entry is None
            else max(entry.complete_through, complete_through(as_of, fetched_at))
        )
        new_entry = CacheEntry(frame=merged, start=new_start, complete_through=new_complete_through)
        save(dataset, symbol, new_entry, settings=settings)
        result = new_entry.frame

    return drop_after(
        result, date_column, as_of, later_rows_expected=True, dataset=dataset, symbol=symbol
    )
