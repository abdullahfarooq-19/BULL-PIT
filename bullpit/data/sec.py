"""SEC EDGAR: ticker-to-CIK, companyfacts, filing-date filtering
(dev-plan.md Part 2, Part 6).

Two requests have no date parameter to filter by (M1-FR-5): the ticker
map and companyfacts. Both are cached as a whole document and filtered
on read instead, with `drop_after` treating every later fact as expected
(the source has no request filter to have ignored).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import httpx
import pandas as pd

from bullpit import __version__
from bullpit.clock import utc_now
from bullpit.config import Settings
from bullpit.data import cache
from bullpit.data.guard import drop_after
from bullpit.errors import DataUnavailable
from bullpit.logging import get_logger

logger = get_logger(__name__)

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/{cik}.json"

# SEC's current ticker map sends XOM to a holding company created in 2026,
# with no filing history. Exxon's original CIK holds every filing and still
# files 10-Qs, so it's right for every as_of (dev-plan M3 D-M3-16).
_CIK_OVERRIDES: dict[str, int] = {"XOM": 34088}

_last_request_at: float | None = None


@dataclass(frozen=True)
class SecFacts:
    ticker: str
    cik: int
    as_of: date
    facts: pd.DataFrame


def sec_user_agent(settings: Settings) -> str:
    """The User-Agent SEC EDGAR asks for: an app identifier plus a contact
    email. Shared by `doctor` and every SEC request here.
    """
    email = settings.sec_contact_email or "unknown@example.com"
    return f"BullPit/{__version__} {email}"


def _get_json(url: str, *, settings: Settings) -> dict[str, Any]:
    """A paced, User-Agent-carrying GET, with the response parsed as JSON.

    Third-party errors become `DataUnavailable` (M1-FR-11, M1-FR-12,
    NFR-4); a 404 does too, since that's how SEC reports "no such CIK" or
    "no companyfacts for this company".
    """
    global _last_request_at
    min_interval = 1.0 / settings.sec_max_requests_per_second
    if _last_request_at is not None:
        wait = min_interval - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
    _last_request_at = time.monotonic()

    logger.info("sec_request", url=url)
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": sec_user_agent(settings)},
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise DataUnavailable(f"SEC request failed for {url}: {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise DataUnavailable(f"SEC request failed for {url}") from exc
    return cast(dict[str, Any], response.json())


def _normalize_ticker(ticker: str) -> str:
    return ticker.upper().replace(".", "-")


def _ticker_map_entry(settings: Settings, *, force_refresh: bool) -> cache.CacheEntry:
    """The cached ticker-to-CIK map, refetched at most once per NY calendar day."""
    current = cache.complete_through(date.max, utc_now())
    entry = None if force_refresh else cache.load("sec", "company_tickers", settings=settings)
    if entry is not None and entry.complete_through >= current:
        return entry

    data = _get_json(_COMPANY_TICKERS_URL, settings=settings)
    rows = [
        {"ticker": _normalize_ticker(row["ticker"]), "cik": int(row["cik_str"])}
        for row in data.values()
    ]
    frame = pd.DataFrame(rows, columns=["ticker", "cik"])
    entry = cache.CacheEntry(frame=frame, start=current, complete_through=current)
    cache.save("sec", "company_tickers", entry, settings=settings)
    return entry


def get_cik(ticker: str, *, settings: Settings) -> int:
    """The company's CIK, from SEC's current ticker map (D-M1-7: no
    point-in-time ticker history)."""
    normalized = _normalize_ticker(ticker)
    if normalized in _CIK_OVERRIDES:
        return _CIK_OVERRIDES[normalized]
    table = _ticker_map_entry(settings, force_refresh=False).frame
    match = table.loc[table["ticker"] == normalized]

    if match.empty:
        table = _ticker_map_entry(settings, force_refresh=True).frame
        match = table.loc[table["ticker"] == normalized]

    if match.empty:
        raise DataUnavailable("No SEC filings found for this ticker. Try a US company stock.")
    return int(match["cik"].iloc[0])


def _flatten(companyfacts: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for taxonomy, tags in companyfacts.get("facts", {}).items():
        for tag, tag_data in tags.items():
            for unit, records in tag_data.get("units", {}).items():
                for record in records:
                    rows.append(
                        {
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "unit": unit,
                            "start": record.get("start"),
                            "end": record["end"],
                            "value": float(record["val"]),
                            "fy": record.get("fy"),
                            "fp": record.get("fp"),
                            "form": record.get("form"),
                            "filed": record["filed"],
                            "accn": record.get("accn"),
                        }
                    )
    columns = [
        "taxonomy",
        "tag",
        "unit",
        "start",
        "end",
        "value",
        "fy",
        "fp",
        "form",
        "filed",
        "accn",
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame["start"] = pd.to_datetime(frame["start"])
    frame["end"] = pd.to_datetime(frame["end"])
    frame["filed"] = pd.to_datetime(frame["filed"])
    return frame


def get_sec_facts(ticker: str, as_of: date, *, settings: Settings) -> SecFacts:
    cik = get_cik(ticker, settings=settings)
    symbol = f"CIK{cik:010d}"

    entry = cache.load("sec_facts", symbol, settings=settings)
    if entry is None or entry.complete_through < as_of:
        data = _get_json(_COMPANYFACTS_URL.format(cik=symbol), settings=settings)
        frame = _flatten(data)
        complete_through = cache.complete_through(date.max, utc_now())
        entry = cache.CacheEntry(frame=frame, start=date.min, complete_through=complete_through)
        cache.save("sec_facts", symbol, entry, settings=settings)

    filtered = drop_after(
        entry.frame, "filed", as_of, later_rows_expected=True, dataset="sec_facts", symbol=ticker
    )
    filtered = filtered.sort_values(["filed", "accn"])
    latest = filtered.drop_duplicates(
        subset=["taxonomy", "tag", "unit", "start", "end"], keep="last"
    ).reset_index(drop=True)
    return SecFacts(ticker=ticker, cik=cik, as_of=as_of, facts=latest)
