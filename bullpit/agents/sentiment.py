"""News sentiment analyst: code selects and de-duplicates headlines; the
LLM scores each one; code combines the scores into a signal (architecture
Part 7; M3-FR-13, FR-14; D-M3-8).
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.data.news import NewsArticle, get_news
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import Evidence, HeadlineScore, HeadlineScores, Signal
from bullpit.state import RequestState
from bullpit.tools.sentiment import select_headlines, weighted_sentiment

_TEMPLATE = "sentiment.md"
_SAFE_DEFAULT = HeadlineScores(scores=[])


def _headline_fact(headline_id: str, article: NewsArticle, score: HeadlineScore) -> Evidence:
    return Evidence(
        id=headline_id,
        fact=(
            f'{article.created_at.date()}: "{article.headline}" '
            f"(score {score.score:+.2f}, relevance {score.relevance:.2f})"
        ),
    )


def sentiment_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    articles = get_news(state.ticker, state.as_of, settings=settings)
    if not articles:
        signal = Signal(
            ticker=state.ticker,
            analyst="sentiment",
            direction="neutral",
            confidence=0.0,
            evidence=[],
            note="no news in the lookback window",
        )
        return {"sentiment_signal": signal}

    pairs = select_headlines(
        [(article.created_at, article.headline) for article in articles],
        max_headlines=settings.news_max_headlines,
        duplicate_similarity=settings.news_duplicate_similarity,
    )
    selected = [(headline_id, articles[index]) for headline_id, index in pairs]
    known_ids = {headline_id for headline_id, _ in selected}

    result = call_llm(
        Role.SMALL,
        _TEMPLATE,
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "headlines": [
                {
                    "id": headline_id,
                    "date": str(article.created_at.date()),
                    "headline": article.headline,
                }
                for headline_id, article in selected
            ],
        },
        HeadlineScores,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    if result.flagged:
        signal = Signal(
            ticker=state.ticker,
            analyst="sentiment",
            direction="neutral",
            confidence=0.0,
            evidence=[],
            flagged=True,
            note="LLM reply invalid after retry",
        )
        return {"sentiment_signal": signal}

    # Unknown ids are ignored; a headline the reply left out is dropped
    # entirely, from both the average and the evidence (M3-FR-14).
    scores_by_id = {score.id: score for score in result.value.scores if score.id in known_ids}
    triples = [(score.id, score.score, score.relevance) for score in scores_by_id.values()]
    direction, confidence = weighted_sentiment(
        known_ids, triples, neutral_band=settings.sentiment_neutral_band
    )
    evidence = [
        _headline_fact(headline_id, article, scores_by_id[headline_id])
        for headline_id, article in selected
        if headline_id in scores_by_id
    ]

    signal = Signal(
        ticker=state.ticker,
        analyst="sentiment",
        direction=direction,
        confidence=confidence,
        evidence=evidence,
    )
    return {"sentiment_signal": signal}
