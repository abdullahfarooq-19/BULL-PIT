"""Number and ID check (M5-AC-3 at check level, AC-4): the allowed formatting
variants pass, invented numbers and unknown IDs are rejected, and masking."""

from __future__ import annotations

import pytest

from bullpit.report.number_check import allowed_numbers, check_text, mask_unknown_numbers

_REPORT = (
    "Buy 32 shares of AAPL, about $5,824.00 (5.8% of equity). Confidence 0.62. "
    "Reference $225.37. Return over 3 months +1.2%. Close above the 200-day average. "
    "Price data 2024-10-18. Evidence T1, F2."
)
_ALLOWED = allowed_numbers(_REPORT)
_REGISTRY = {"T1", "F2"}


@pytest.mark.parametrize(
    "text",
    [
        "$5,824",
        "5824",
        "5,824.00",
        "5.8%",
        "$225",
        "+1.2%",
        "-1.2%",
        "32 shares",
        "confidence 0.62",
        "the 200-day average",
        "as of 2024-10-18",
        "cites (T1, F2)",
    ],
)
def test_accepts_variants(text: str) -> None:
    assert check_text(text, _ALLOWED, _REGISTRY) == []


@pytest.mark.parametrize(
    ("text", "rejected"),
    [
        ("target $200", ["$200"]),
        ("about 5.9%", ["5.9%"]),
        ("about $226", ["$226"]),
        ("confidence 1", ["1"]),
        ("6% of equity", ["6%"]),
        ("as of 2024-10-19", ["2024-10-19"]),
        ("see T99", ["T99"]),
        ("$200, then $200 again, T99", ["$200", "T99"]),
    ],
)
def test_rejects(text: str, rejected: list[str]) -> None:
    assert check_text(text, _ALLOWED, _REGISTRY) == rejected


def test_mask_unknown_numbers() -> None:
    text = "Target $200 and 5.8% on 2024-10-19, per T1 and T99."
    assert mask_unknown_numbers(text, _ALLOWED) == "Target [?] and 5.8% on [?], per T1 and T99."


# U+2010 hyphen, U+2011 non-breaking hyphen, U+2012 figure dash, U+2013 en dash, U+2014 em dash
@pytest.mark.parametrize("hyphen", [chr(code) for code in range(0x2010, 0x2015)])
def test_a_date_with_a_typographic_hyphen_is_the_same_date(hyphen: str) -> None:
    """Found on a real GOOGL report: a date typed with non-breaking hyphens was read as three
    loose numbers, so the whole report prose fell back to code wording."""
    date = f"2024{hyphen}10{hyphen}18"
    other = f"2024{hyphen}10{hyphen}19"
    assert check_text(f"as of {date}", _ALLOWED, _REGISTRY) == []
    assert check_text(f"as of {other}", _ALLOWED, _REGISTRY) == [other]
    assert mask_unknown_numbers(f"on {date} and {other}", _ALLOWED) == f"on {date} and [?]"
    assert allowed_numbers(f"Filed {date}").dates == {"2024-10-18"}
