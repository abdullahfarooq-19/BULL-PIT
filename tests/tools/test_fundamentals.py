"""Hand-built fact-table checks (M3-AC-3)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from bullpit.tools.fundamentals import compute_fundamentals


def _facts(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["start"] = pd.to_datetime(frame["start"])
    frame["end"] = pd.to_datetime(frame["end"])
    frame["filed"] = pd.to_datetime(frame["filed"])
    return frame


def _row(
    tag: str, start: str, end: str, value: float, filed: str, form: str = "10-Q"
) -> dict[str, Any]:
    return {
        "taxonomy": "us-gaap",
        "tag": tag,
        "unit": "USD",
        "start": start,
        "end": end,
        "value": value,
        "fy": None,
        "fp": None,
        "form": form,
        "filed": filed,
        "accn": "0001-24-000001",
    }


class TestQuarterlyMetrics:
    """Four clean quarters plus the year-ago quarter: growth, margin, TTM EPS, P/E."""

    def test_growth_margin_ttm_eps_and_pe(self) -> None:
        rows = [
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2023-04-01", "2023-06-30", 100.0, "2023-08-01"),
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2023-07-01", "2023-09-30", 101.0, "2023-11-01"),
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2023-10-01", "2023-12-31", 102.0, "2024-02-01"),
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2024-01-01", "2024-03-31", 103.0, "2024-05-01"),
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2024-04-01", "2024-06-30", 110.0, "2024-08-01"),
            _row("NetIncomeLoss", "2024-04-01", "2024-06-30", 27.5, "2024-08-01"),
            _row("EarningsPerShareDiluted", "2023-07-01", "2023-09-30", 1.0, "2023-11-01"),
            _row("EarningsPerShareDiluted", "2023-10-01", "2023-12-31", 1.1, "2024-02-01"),
            _row("EarningsPerShareDiluted", "2024-01-01", "2024-03-31", 1.2, "2024-05-01"),
            _row("EarningsPerShareDiluted", "2024-04-01", "2024-06-30", 1.3, "2024-08-01"),
        ]  # fmt: skip
        metrics = compute_fundamentals(_facts(rows), reference_price=184.0, splits=[])

        assert metrics.latest_quarter_end == date(2024, 6, 30)
        assert metrics.latest_revenue == pytest.approx(110.0)
        assert metrics.revenue_growth_yoy == pytest.approx(0.10)
        assert metrics.latest_net_income == pytest.approx(27.5)
        assert metrics.net_margin == pytest.approx(0.25)
        assert metrics.ttm_eps == pytest.approx(4.6)
        assert metrics.pe == pytest.approx(40.0)
        assert metrics.filing_form == "10-Q"
        assert metrics.filing_date == date(2024, 8, 1)


class TestQ4DerivedFromAnnual:
    """The latest quarter exists only as FY total minus Q1..Q3 (the MSFT case)."""

    def test_q4_is_fy_minus_first_three_quarters(self) -> None:
        rows = [
            _row("Revenues", "2023-07-01", "2023-09-30", 50.0, "2023-11-01"),
            _row("Revenues", "2023-10-01", "2023-12-31", 55.0, "2024-02-01"),
            _row("Revenues", "2024-01-01", "2024-03-31", 60.0, "2024-05-01"),
            _row("Revenues", "2023-07-01", "2024-06-30", 230.0, "2024-08-15", form="10-K"),
        ]
        metrics = compute_fundamentals(_facts(rows), reference_price=100.0, splits=[])

        assert metrics.latest_quarter_end == date(2024, 6, 30)
        assert metrics.latest_revenue == pytest.approx(65.0)  # 230 - (50+55+60)
        assert metrics.filing_form == "10-K"
        assert metrics.filing_date == date(2024, 8, 15)
        # No quarter ~1 year before 2024-06-30 exists in this fixture.
        assert metrics.revenue_growth_yoy is None


class TestTagChoiceDoesNotMixDefinitions:
    """Two revenue tags with different reach (the XOM case, sec7.1 C-1):
    the tag reaching the latest quarter is used for every period, including
    the year-ago comparison — never the other tag's value."""

    def test_uses_one_tag_throughout(self) -> None:
        rows = [
            # Old tag: stopped being filed after 2023-06-30. Its value at
            # that date (999.0) must never be used as the year-ago figure.
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2022-04-01", "2022-06-30", 900.0, "2022-08-01"),
            _row("RevenueFromContractWithCustomerExcludingAssessedTax",
                 "2023-04-01", "2023-06-30", 999.0, "2023-08-01"),
            # Current tag: the only one reaching the latest quarter.
            _row("Revenues", "2023-04-01", "2023-06-30", 200.0, "2023-08-01"),
            _row("Revenues", "2024-04-01", "2024-06-30", 220.0, "2024-08-01"),
        ]  # fmt: skip
        metrics = compute_fundamentals(_facts(rows), reference_price=100.0, splits=[])

        assert metrics.latest_revenue == pytest.approx(220.0)
        assert metrics.revenue_growth_yoy == pytest.approx(0.10)  # 220/200 - 1, not 220/999 - 1


class TestEpsSplitAdjustedAndNegativePe:
    """EPS filed before a 10:1 split is divided by 10; a negative TTM EPS
    gives pe=None (D-M3-11)."""

    def test_split_adjustment_and_negative_ttm_eps(self) -> None:
        rows = [
            _row("Revenues", "2024-04-01", "2024-06-30", 500.0, "2024-08-01"),
            _row("EarningsPerShareDiluted", "2023-07-01", "2023-09-30", 100.0, "2023-11-01"),
            _row("EarningsPerShareDiluted", "2023-10-01", "2023-12-31", 100.0, "2024-02-01"),
            _row("EarningsPerShareDiluted", "2024-01-01", "2024-03-31", 100.0, "2024-05-01"),
            # Filed after the split's ex-date: already on the post-split basis.
            _row("EarningsPerShareDiluted", "2024-04-01", "2024-06-30", -1000.0, "2024-08-01"),
        ]
        metrics = compute_fundamentals(
            _facts(rows), reference_price=50.0, splits=[(date(2024, 6, 10), 10.0)]
        )

        # (100/10) + (100/10) + (100/10) + (-1000/1) = -970.0
        assert metrics.ttm_eps == pytest.approx(-970.0)
        assert metrics.pe is None
