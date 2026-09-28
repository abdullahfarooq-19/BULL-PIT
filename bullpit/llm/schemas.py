"""Base LLM reply schemas (M2 specs-plan sec5.3; architecture Part 3, Part 5).

Every M3+ agent schema extends or composes these. M2 doesn't call an
analyst itself; they live here because they're shared, not owned by any
one caller.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
