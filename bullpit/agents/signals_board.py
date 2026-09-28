"""Signals board: validates and summarises the three analyst signals
(architecture Part 8; M3-FR-16). Code only.
"""

from __future__ import annotations

from bullpit.llm.schemas import Evidence, Signal
from bullpit.state import SignalsBoard

_DIRECTION_VALUE = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}
_EVIDENCE_PREFIX = {"technical": "T", "fundamentals": "F", "sentiment": "S"}


def _has_conflict(signals: dict[str, Signal], *, min_confidence: float) -> bool:
    has_bullish = any(
        s.direction == "bullish" and s.confidence >= min_confidence for s in signals.values()
    )
    has_bearish = any(
        s.direction == "bearish" and s.confidence >= min_confidence for s in signals.values()
    )
    return has_bullish and has_bearish


def build_board(signals: dict[str, Signal], *, conflict_min_confidence: float) -> SignalsBoard:
    """`signals` holds exactly one signal per analyst, keyed by analyst name."""
    score = (
        sum(_DIRECTION_VALUE[signal.direction] * signal.confidence for signal in signals.values())
        / 3
    )

    evidence: dict[str, Evidence] = {}
    for analyst, signal in signals.items():
        prefix = _EVIDENCE_PREFIX[analyst]
        for item in signal.evidence:
            if not item.id.startswith(prefix):
                raise ValueError(
                    f"{analyst} evidence {item.id!r} does not have the expected prefix {prefix!r}"
                )
            if item.id in evidence:
                raise ValueError(f"duplicate evidence id {item.id!r}")
            evidence[item.id] = item

    conflict = _has_conflict(signals, min_confidence=conflict_min_confidence)
    return SignalsBoard(signals=signals, score=score, conflict=conflict, evidence=evidence)
