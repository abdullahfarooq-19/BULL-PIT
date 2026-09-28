"""Happy-path test for the journal engine and models (dev-plan.md sec7.2)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from bullpit.journal.db import make_engine, make_sessions
from bullpit.journal.models import Base, LLMCall, Request


def test_insert_and_read_back_request_and_llm_call() -> None:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = make_sessions(engine)

    now = datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)
    with sessions() as session:
        session.add(
            Request(
                id="req-1",
                mode="live",
                as_of=date(2026, 9, 28),
                created_at=now,
                ticker="AAPL",
                status="completed",
            )
        )
        session.add(
            LLMCall(
                request_id="req-1",
                role="small",
                model="openai/gpt-oss-20b",
                prompt_version="abcdef012345",
                cache_hit=False,
                cache_key="deadbeef",
                input_tokens=100,
                output_tokens=20,
                reasoning_tokens=5,
                latency_ms=250,
                flagged=False,
                created_at=now,
            )
        )
        session.commit()

    with sessions() as session:
        request = session.get(Request, "req-1")
        assert request is not None
        assert request.mode == "live"
        assert request.as_of == date(2026, 9, 28)

        [call] = session.query(LLMCall).all()
        assert call.request_id == "req-1"
        assert call.model == "openai/gpt-oss-20b"
        assert call.input_tokens == 100
        assert call.cache_hit is False
