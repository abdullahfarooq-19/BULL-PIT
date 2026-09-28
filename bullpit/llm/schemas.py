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
