"""Base LLM reply schemas (M2 specs-plan sec5.3; architecture Part 3, Part 5).

Every M3+ agent schema extends or composes these. M2 doesn't call an
analyst itself; they live here because they're shared, not owned by any
one caller.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Evidence(BaseModel):
    id: str  # e.g. "T1", assigned by code, never by the LLM
    fact: str


class Signal(BaseModel):
    ticker: str
    analyst: str
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]
    flagged: bool = False  # the analyst failed, or its LLM reply was the safe default
    note: str | None = None  # why it's flagged, or thin (M3-FR-15)


class AnalystVerdict(BaseModel):
    """Technical and fundamentals LLM reply (M3-FR-9, FR-11; D-M3-1): the
    LLM only judges direction and confidence over code-written evidence."""

    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)


class HeadlineScore(BaseModel):
    id: str
    score: float = Field(ge=-1.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)


class HeadlineScores(BaseModel):
    """Sentiment LLM reply (M3-FR-14): a score and relevance per headline id."""

    scores: list[HeadlineScore]


class DebatePoint(BaseModel):
    """One claim from a debate turn (M4-FR-2, FR-3): code checks
    `evidence_ids` against the board's registry after the reply comes back."""

    claim: str
    evidence_ids: list[str]


class DebateReply(BaseModel):
    """Bull/bear LLM reply (M4-FR-2)."""

    points: list[DebatePoint]
    concessions: list[str]
    conviction: float = Field(ge=0.0, le=1.0)


class TraderReply(BaseModel):
    """Trader LLM reply (architecture Part 10, minus `ticker`: code fills it
    in from the request, D-M4-5)."""

    action: Literal["buy", "no_trade"]
    target_weight: float = Field(ge=0.0, le=1.0)
    exit_style: Literal["tight", "normal", "wide"]
    confidence: float = Field(ge=0.0, le=1.0)
    decisive_evidence: list[str]
    reasoning: str


class RiskReviewReply(BaseModel):
    """Stage B LLM reply (M4-FR-11). `shrink` requires `shares`; an invalid
    combination fails validation, so it gets the gateway's own retry
    (D-M4-10) rather than a second, risk-specific check."""

    decision: Literal["approve", "shrink", "veto"]
    shares: int | None = Field(default=None, ge=1)
    reason: str

    @model_validator(mode="after")
    def _shrink_requires_shares(self) -> RiskReviewReply:
        if self.decision == "shrink" and self.shares is None:
            raise ValueError("a 'shrink' decision requires 'shares'")
        return self
