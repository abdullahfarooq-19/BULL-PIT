"""Fundamentals math: quarterly figures, YoY growth, margin, TTM EPS, P/E
(architecture Part 6; M3-FR-10, FR-11, FR-12; D-M3-11).

Pure over a SEC facts frame (bullpit/data/sec.py SecFacts.facts) and a
splits list (bullpit/data/prices.py PriceHistory.splits): no I/O, no
settings (dev-plan.md sec2.2: pure core; NFR-3). Period lengths are named
constants, not settings (D-M3-10): they define what "a quarter" means.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Any, cast

import pandas as pd
from pydantic import BaseModel

_QUARTER_DAYS = (80, 100)
_YEAR_DAYS = (350, 380)
_YEAR_AGO_DAYS = (355, 375)
_TTM_QUARTERS = 4

# Ordered candidate list per metric (M3-FR-10; §7.1 C-1): the tag whose
# series reaches the latest quarter wins, so growth, margin and TTM EPS
# never mix two tags' definitions of the same metric.
_REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenuesNetOfInterestExpense",
    "SalesRevenueNet",
]
_NET_INCOME_TAG = "NetIncomeLoss"
_EPS_TAG = "EarningsPerShareDiluted"


@dataclass(frozen=True)
class _Quarter:
    start: date
    end: date
    value: float
    filed: date
    form: str


class FundamentalsMetrics(BaseModel, frozen=True):
    latest_quarter_end: date | None
    latest_revenue: float | None
    revenue_growth_yoy: float | None
    latest_net_income: float | None
    net_margin: float | None
    ttm_eps: float | None
    pe: float | None
    filing_form: str | None
    filing_period_end: date | None
    filing_date: date | None


_EMPTY = FundamentalsMetrics(
    latest_quarter_end=None,
    latest_revenue=None,
    revenue_growth_yoy=None,
    latest_net_income=None,
    net_margin=None,
    ttm_eps=None,
    pe=None,
    filing_form=None,
    filing_period_end=None,
    filing_date=None,
)


def _duration_rows(facts: pd.DataFrame, tag: str) -> list[dict[str, Any]]:
    """Rows for `tag` that have both a start and an end (instant facts,
    e.g. balance-sheet items, have no start and are never a quarter or year)."""
    rows = facts.loc[(facts["tag"] == tag) & facts["start"].notna()]
    return cast("list[dict[str, Any]]", rows.to_dict("records"))


def _series_for_tag(facts: pd.DataFrame, tag: str) -> dict[date, _Quarter]:
    """Discrete quarters for `tag`, plus any Q4 derivable as FY - (Q1+Q2+Q3)
    (M3-FR-10). Facts are already deduped to the latest filed value per
    period by `bullpit/data/sec.py`."""
    quarters: dict[date, _Quarter] = {}
    years: list[dict[str, Any]] = []
    for row in _duration_rows(facts, tag):
        start: date = row["start"].date()
        end: date = row["end"].date()
        days = (end - start).days
        if _QUARTER_DAYS[0] <= days <= _QUARTER_DAYS[1]:
            quarters[end] = _Quarter(
                start, end, float(row["value"]), row["filed"].date(), row["form"]
            )
        elif _YEAR_DAYS[0] <= days <= _YEAR_DAYS[1]:
            years.append(row)

    for row in years:
        start, end = row["start"].date(), row["end"].date()
        if end in quarters:
            continue
        inside = sorted(
            (q for q in quarters.values() if q.start >= start and q.end < end),
            key=lambda q: q.end,
        )
        if len(inside) == 3:
            q4_value = float(row["value"]) - sum(q.value for q in inside)
            quarters[end] = _Quarter(
                inside[-1].end, end, q4_value, row["filed"].date(), row["form"]
            )
    return quarters


def _select_tag(facts: pd.DataFrame, candidates: list[str]) -> dict[date, _Quarter] | None:
    """The candidate tag whose series reaches the latest quarter (ties: list order)."""
    best: dict[date, _Quarter] | None = None
    best_end: date | None = None
    for tag in candidates:
        series = _series_for_tag(facts, tag)
        if not series:
            continue
        latest_end = max(series)
        if best_end is None or latest_end > best_end:
            best, best_end = series, latest_end
    return best


def _year_ago(series: dict[date, _Quarter], latest_end: date) -> _Quarter | None:
    for end, quarter in series.items():
        days_back = (latest_end - end).days
        if _YEAR_AGO_DAYS[0] <= days_back <= _YEAR_AGO_DAYS[1]:
            return quarter
    return None


def _ttm_eps(series: dict[date, _Quarter], splits: list[tuple[date, float]]) -> float | None:
    """Sum of the last 4 consecutive quarters' diluted EPS, each split-adjusted
    to today's share basis (M3-FR-10)."""
    ordered = sorted(series.values(), key=lambda q: q.end)
    if len(ordered) < _TTM_QUARTERS:
        return None
    last_four = ordered[-_TTM_QUARTERS:]
    for previous, current in pairwise(last_four):
        gap = (current.end - previous.end).days
        if not (_QUARTER_DAYS[0] <= gap <= _QUARTER_DAYS[1]):
            return None

    total = 0.0
    for quarter in last_four:
        factor = 1.0
        for ex_date, ratio in splits:
            if quarter.filed < ex_date:
                factor *= ratio
        total += quarter.value / factor
    return total


def compute_fundamentals(
    facts: pd.DataFrame,
    *,
    reference_price: float,
    splits: list[tuple[date, float]],
) -> FundamentalsMetrics:
    """`facts` is `us-gaap` rows from `SecFacts.facts`, already filtered to
    on-or-before `as_of` and deduped to the latest filed value per period.
    `reference_price` is the latest close up to `as_of` (M3-FR-10).
    """
    revenue_series = _select_tag(facts, _REVENUE_TAGS)
    if revenue_series is None:
        return _EMPTY

    latest_end = max(revenue_series)
    latest = revenue_series[latest_end]

    year_ago = _year_ago(revenue_series, latest_end)
    growth = None if year_ago is None or year_ago.value == 0 else latest.value / year_ago.value - 1

    net_income_series = _series_for_tag(facts, _NET_INCOME_TAG)
    net_income_quarter = net_income_series.get(latest_end)
    margin = (
        None
        if net_income_quarter is None or latest.value == 0
        else net_income_quarter.value / latest.value
    )

    eps_series = _series_for_tag(facts, _EPS_TAG)
    ttm_eps = _ttm_eps(eps_series, splits)
    pe = reference_price / ttm_eps if ttm_eps is not None and ttm_eps > 0 else None

    return FundamentalsMetrics(
        latest_quarter_end=latest_end,
        latest_revenue=latest.value,
        revenue_growth_yoy=growth,
        latest_net_income=None if net_income_quarter is None else net_income_quarter.value,
        net_margin=margin,
        ttm_eps=ttm_eps,
        pe=pe,
        filing_form=latest.form,
        filing_period_end=latest_end,
        filing_date=latest.filed,
    )
