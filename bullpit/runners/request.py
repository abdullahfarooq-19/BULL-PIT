"""Runs one request end to end: the training-cutoff check, the duplicate
lock, the graph, and recording the result to the journal (architecture
sec5; M3-FR-1 to FR-3, FR-15, FR-18 to FR-20; D-M3-9, D-M3-13).
"""

from __future__ import annotations

import secrets
import shutil
import subprocess
from datetime import date, datetime, timedelta
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from bullpit.broker.base import Broker
from bullpit.clock import Clock, utc_now
from bullpit.config import Settings
from bullpit.graph import Deps, build_graph
from bullpit.journal.models import (
    DebateTurnRecord,
    RecommendationRecord,
    ReportRecord,
    Request,
    SignalRecord,
)
from bullpit.llm.gateway import CompletionFn, litellm_completion
from bullpit.logging import get_logger
from bullpit.state import RequestState, TradeAttempt

logger = get_logger(__name__)

_SECRET_CONFIG_FIELDS = {
    "alpaca_api_key",
    "alpaca_secret_key",
    "groq_api_key",
    "sec_contact_email",
    "langfuse_public_key",
    "langfuse_secret_key",
}


def naive_utc_now() -> datetime:
    return utc_now().replace(tzinfo=None)


def earliest_backtest_date(settings: Settings) -> date:
    latest_cutoff = max(settings.llm_small_model_cutoff, settings.llm_large_model_cutoff)
    return latest_cutoff + timedelta(days=1)


def _config_snapshot(settings: Settings) -> dict[str, Any]:
    dumped = settings.model_dump(mode="json")
    return {key: value for key, value in dumped.items() if key not in _SECRET_CONFIG_FIELDS}


def git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        result = subprocess.run(  # noqa: S603 - a fixed, argument-free git command
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    commit = result.stdout.strip()
    return commit or "unknown"


def _insert_rejected_row(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    ticker: str,
    mode: str,
    as_of: date,
    message: str,
    settings: Settings,
) -> None:
    with sessions() as session:
        session.add(
            Request(
                id=request_id,
                mode=mode,
                as_of=as_of,
                created_at=naive_utc_now(),
                ticker=ticker,
                status="rejected",
                status_reason=message,
                config=_config_snapshot(settings),
                git_commit=git_commit(),
                finished_at=naive_utc_now(),
            )
        )
        session.commit()


def _acquire_lock(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    ticker: str,
    mode: str,
    as_of: date,
    timeout_minutes: int,
) -> str | None:
    """Marks abandoned `running` rows failed, then inserts this request's
    `running` row, all in one transaction. Returns `None` once the row is
    committed, or the FR-5 duplicate message if another request is
    genuinely still running (M3-FR-3).
    """
    with sessions() as session:
        cutoff = naive_utc_now() - timedelta(minutes=timeout_minutes)
        stale = (
            session.execute(
                select(Request).where(
                    Request.ticker == ticker, Request.mode == mode, Request.status == "running"
                )
            )
            .scalars()
            .all()
        )
        for row in stale:
            created = row.created_at.replace(tzinfo=None)
            if created < cutoff:
                row.status = "failed"
                row.status_reason = "abandoned: running longer than the lock timeout"
                row.finished_at = naive_utc_now()
                logger.warning(
                    "request_lock_abandoned", ticker=ticker, mode=mode, request_id=row.id
                )

        session.add(
            Request(
                id=request_id,
                mode=mode,
                as_of=as_of,
                created_at=naive_utc_now(),
                ticker=ticker,
                status="running",
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return f"A {mode} request for {ticker} is already running."
    return None


def _recommendation_record(
    request_id: str, index: int, attempt: TradeAttempt, *, final_order: Any | None
) -> RecommendationRecord:
    recommendation = attempt.recommendation
    verdict = attempt.verdict
    return RecommendationRecord(
        request_id=request_id,
        attempt=index,
        action=recommendation.action,
        exit_style=recommendation.exit_style,
        target_weight=str(recommendation.target_weight),
        confidence=recommendation.confidence,
        decisive_evidence=list(recommendation.decisive_evidence),
        reasoning=recommendation.reasoning,
        flagged=recommendation.flagged,
        sized_order=None
        if attempt.sized_order is None
        else attempt.sized_order.model_dump(mode="json"),
        blocked_reason=attempt.blocked_reason,
        review_decision=None if verdict is None else verdict.decision,
        review_reason=None if verdict is None else verdict.reason,
        review_shares=None if verdict is None else verdict.requested_shares,
        review_clamped=None if verdict is None else verdict.clamped,
        review_flagged=None if verdict is None else verdict.flagged,
        final_order=final_order,
    )


def add_request_rows(
    session: Session,
    row: Request,
    *,
    result: RequestState | None,
    error: BaseException | None,
    settings: Settings,
) -> None:
    """Fills in `row` and adds the request's child rows. The caller commits, so
    the backtest runner can commit a week's requests with its checkpoint."""
    request_id = row.id
    if error is not None:
        row.status = "failed"
        row.status_reason = str(error)
    elif result is not None and result.rejection is not None:
        row.status = "rejected"
        row.status_reason = result.rejection
    else:
        row.status = "completed"

    row.route = None if result is None else result.route
    row.warnings = None if result is None else list(result.warnings)
    row.config = _config_snapshot(settings)
    row.git_commit = git_commit()
    row.price_source = None if result is None or result.prices is None else result.prices.source
    row.finished_at = naive_utc_now()
    row.outcome = None if result is None else result.outcome
    row.no_trade_reason = None if result is None else result.no_trade_reason
    session.flush()  # the models have no relationships, so write the row before its children

    if result is not None:
        for signal in (
            result.technical_signal,
            result.fundamentals_signal,
            result.sentiment_signal,
        ):
            if signal is None:
                continue
            session.add(
                SignalRecord(
                    request_id=request_id,
                    analyst=signal.analyst,
                    direction=signal.direction,
                    confidence=signal.confidence,
                    evidence=[item.model_dump() for item in signal.evidence],
                    flagged=signal.flagged,
                    note=signal.note,
                )
            )

        for turn in result.debate:
            session.add(
                DebateTurnRecord(
                    request_id=request_id,
                    round=turn.round,
                    side=turn.side,
                    points=[point.model_dump() for point in turn.points],
                    concessions=list(turn.concessions),
                    conviction=turn.conviction,
                    word_count=turn.word_count,
                    unsupported_count=sum(1 for point in turn.points if point.unsupported),
                    over_word_limit=turn.over_word_limit,
                    flagged=turn.flagged,
                )
            )

        last_index = len(result.attempts) - 1
        for index, attempt in enumerate(result.attempts):
            is_winning_attempt = result.outcome == "buy" and index == last_index
            final_order = (
                result.sized_order.model_dump(mode="json")
                if is_winning_attempt and result.sized_order is not None
                else None
            )
            session.add(
                _recommendation_record(request_id, index + 1, attempt, final_order=final_order)
            )

        if result.report is not None:
            session.add(
                ReportRecord(request_id=request_id, report=result.report.model_dump(mode="json"))
            )


def _finalize(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    result: RequestState | None,
    error: BaseException | None,
    settings: Settings,
) -> None:
    with sessions() as session:
        row = session.get(Request, request_id)
        if row is None:
            raise ValueError(f"no requests row for {request_id!r} to finalize")
        add_request_rows(session, row, result=result, error=error, settings=settings)
        session.commit()


def run_request(
    ticker: str,
    mode: Literal["live", "backtest"],
    clock: Clock,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    broker: Broker,
    completion_fn: CompletionFn = litellm_completion,
) -> RequestState:
    as_of = clock.as_of()
    ticker = ticker.upper()
    request_id = f"{as_of:%Y%m%d}-{ticker}-{secrets.token_hex(4)}"

    with structlog.contextvars.bound_contextvars(
        request_id=request_id, mode=mode, as_of=str(as_of)
    ):
        latest_cutoff = max(settings.llm_small_model_cutoff, settings.llm_large_model_cutoff)
        if mode == "backtest" and as_of <= latest_cutoff:
            message = (
                "Backtest dates must be after the models' training cutoff: "
                f"use {earliest_backtest_date(settings)} or later."
            )
            _insert_rejected_row(
                sessions,
                request_id=request_id,
                ticker=ticker,
                mode=mode,
                as_of=as_of,
                message=message,
                settings=settings,
            )
            return RequestState(
                request_id=request_id, mode=mode, as_of=as_of, ticker=ticker, rejection=message
            )

        duplicate_message = _acquire_lock(
            sessions,
            request_id=request_id,
            ticker=ticker,
            mode=mode,
            as_of=as_of,
            timeout_minutes=settings.request_lock_timeout_minutes,
        )
        if duplicate_message is not None:
            _insert_rejected_row(
                sessions,
                request_id=request_id,
                ticker=ticker,
                mode=mode,
                as_of=as_of,
                message=duplicate_message,
                settings=settings,
            )
            return RequestState(
                request_id=request_id,
                mode=mode,
                as_of=as_of,
                ticker=ticker,
                rejection=duplicate_message,
            )

        deps = Deps(
            settings=settings, sessions=sessions, broker=broker, completion_fn=completion_fn
        )
        graph = build_graph(deps)

        result: RequestState | None = None
        error: BaseException | None = None
        try:
            raw_state = graph.invoke(
                RequestState(request_id=request_id, mode=mode, as_of=as_of, ticker=ticker)
            )
            result = RequestState.model_validate(raw_state)
        except BaseException as exc:
            error = exc
        finally:
            _finalize(
                sessions, request_id=request_id, result=result, error=error, settings=settings
            )

        if error is not None:
            raise error
        if result is None:  # pragma: no cover - unreachable: error is None => result was set
            raise RuntimeError("run_request finished with neither a result nor an error")
        return result
