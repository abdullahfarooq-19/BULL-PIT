"""Sentiment tools: duplicate removal, headline selection, and the
relevance-weighted average that turns per-headline LLM scores into a
signal (architecture Part 7; M3-FR-13, FR-14). Pure: no I/O, and no
dependency on `bullpit/data` or `bullpit/llm` (dev-plan.md NFR-3) --
callers pass plain headline text and (id, score, relevance) triples.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Literal

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(headline: str) -> set[str]:
    return set(_WORD_RE.findall(headline.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def select_headlines(
    articles: Sequence[tuple[datetime, str]],
    *,
    max_headlines: int,
    duplicate_similarity: float,
) -> list[tuple[str, int]]:
    """`articles` is (created_at, headline) pairs, any order.

    Returns (evidence id, index into `articles`) pairs: newest first, a
    headline whose word set is at least `duplicate_similarity` Jaccard-similar
    to one already kept is dropped, capped at `max_headlines`, numbered S1
    (newest) onward (M3-FR-13).
    """
    order = sorted(range(len(articles)), key=lambda i: articles[i][0], reverse=True)
    kept_indices: list[int] = []
    kept_words: list[set[str]] = []
    for index in order:
        words = _words(articles[index][1])
        if any(_jaccard(words, existing) >= duplicate_similarity for existing in kept_words):
            continue
        kept_indices.append(index)
        kept_words.append(words)
        if len(kept_indices) >= max_headlines:
            break
    return [(f"S{position + 1}", index) for position, index in enumerate(kept_indices)]


def weighted_sentiment(
    known_ids: set[str],
    scores: Iterable[tuple[str, float, float]],
    *,
    neutral_band: float,
) -> tuple[Literal["bullish", "bearish", "neutral"], float]:
    """`scores` is (id, score, relevance) triples from the LLM reply; an id
    not in `known_ids` is ignored (M3-FR-14). Returns (direction, confidence),
    with confidence = |weighted average| and no news -> neutral, 0.0.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for headline_id, score, relevance in scores:
        if headline_id not in known_ids:
            continue
        total_weight += relevance
        weighted_sum += relevance * score
    if total_weight == 0:
        return "neutral", 0.0
    s = weighted_sum / total_weight
    if s > neutral_band:
        return "bullish", abs(s)
    if s < -neutral_band:
        return "bearish", abs(s)
    return "neutral", abs(s)
