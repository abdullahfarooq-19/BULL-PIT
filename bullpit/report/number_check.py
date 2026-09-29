"""Number and evidence-ID check for LLM-written report text (architecture
Part 12; M5-FR-6; D-M5-3; algorithm in M5 specs-plan sec11.1).

Pure and standard-library only. The allowed set is whatever numbers the
code-written report already shows; text passes only if every number and
date in it is one of those (formatting variants allowed) and every evidence
ID is in the board's registry.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Unit = Literal["money", "percent", "plain"]

# One scan, leftmost match wins: an ID or date is consumed before its digits
# could be read as a number.
_TOKEN_RE = re.compile(
    r"(?P<id>\b[TFS]\d+\b)"
    r"|(?P<date>\b\d{4}-\d{2}-\d{2}\b)"
    r"|(?P<number>[-+\N{MINUS SIGN}]?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?)"
)
_MASK = "[?]"
_MIN_EXACT_SIGNIFICANT_DIGITS = 2


@dataclass(frozen=True)
class AllowedNumbers:
    """Values (sign dropped) the report shows, per unit, and its ISO dates."""

    money: frozenset[Decimal]
    percent: frozenset[Decimal]
    plain: frozenset[Decimal]
    dates: frozenset[str]


def _scan(text: str) -> Iterator[re.Match[str]]:
    return _TOKEN_RE.finditer(text)


def _unit(token: str) -> Unit:
    if token.endswith("%"):
        return "percent"
    return "money" if "$" in token else "plain"


def _digits(token: str) -> str:
    return re.sub(r"[^\d.]", "", token)


def allowed_numbers(text: str) -> AllowedNumbers:
    """Collects every number and date in `text` (the code-only report)."""
    values: dict[Unit, set[Decimal]] = {"money": set(), "percent": set(), "plain": set()}
    dates: set[str] = set()
    for match in _scan(text):
        if match["date"]:
            dates.add(match["date"])
        elif match["number"]:
            values[_unit(match["number"])].add(Decimal(_digits(match["number"])))
    return AllowedNumbers(
        money=frozenset(values["money"]),
        percent=frozenset(values["percent"]),
        plain=frozenset(values["plain"]),
        dates=frozenset(dates),
    )


def _number_allowed(token: str, allowed: AllowedNumbers) -> bool:
    """A token may be less precise than an allowed value (rounded half up),
    never more; a one-significant-digit token must match exactly (D-M5-3)."""
    unit = _unit(token)
    digits = _digits(token)
    value = Decimal(digits)
    places = len(digits.partition(".")[2])
    significant = len(digits.replace(".", "").lstrip("0"))
    candidates = (
        allowed.money | allowed.percent | allowed.plain
        if unit == "plain"
        else getattr(allowed, unit)
    )
    step = Decimal(1).scaleb(-places)
    for candidate in candidates:
        if candidate.quantize(step, rounding=ROUND_HALF_UP) != value:
            continue
        if significant >= _MIN_EXACT_SIGNIFICANT_DIGITS or candidate == value:
            return True
    return False


def check_text(text: str, allowed: AllowedNumbers, registry: Collection[str]) -> list[str]:
    """Rejected tokens in order of appearance, as written; empty = passes."""
    rejected: list[str] = []
    for match in _scan(text):
        token = match[0]
        if match["id"]:
            ok = token in registry
        elif match["date"]:
            ok = token in allowed.dates
        else:
            ok = _number_allowed(token, allowed)
        if not ok and token not in rejected:
            rejected.append(token)
    return rejected


def mask_unknown_numbers(text: str, allowed: AllowedNumbers) -> str:
    """Replaces every number or date not in `allowed` with `[?]`. IDs are kept:
    the debate's own unsupported-ID check already covers them."""

    def replace(match: re.Match[str]) -> str:
        token = match[0]
        if match["id"]:
            return token
        ok = token in allowed.dates if match["date"] else _number_allowed(token, allowed)
        return token if ok else _MASK

    return _TOKEN_RE.sub(replace, text)
