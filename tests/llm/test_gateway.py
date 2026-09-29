"""Gateway tests (M2 specs-plan sec13): retries, cache, validation fallback,
quota and the per-call size ceiling, all against the fake provider, an
in-memory journal and a recording `sleep` (dev-plan.md sec7.1).
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    ServiceUnavailableError,
)
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bullpit.clock import utc_now
from bullpit.config import Settings
from bullpit.errors import BullPitError, LLMUnavailable, PromptTooLarge, QuotaExhausted
from bullpit.journal.models import LLMCall
from bullpit.llm.gateway import (
    CompletionReply,
    CompletionRequest,
    ProviderTransient,
    RateLimited,
    Role,
    call_llm,
    litellm_completion,
)
from tests.llm.fake_provider import FakeProvider

TEMPLATE = "measurement_probe.md"
VARIABLES = {"ticker": "AAPL", "indicators": {"RSI14": 55.0}}


class _Probe(BaseModel):
    direction: str
    confidence: float


_SAFE_DEFAULT = _Probe(direction="neutral", confidence=0.0)


def _kwargs(
    settings: Settings,
    sessions: sessionmaker[Session],
    provider: FakeProvider,
    *,
    role: Role = Role.SMALL,
    request_id: str = "req-1",
    seed: int | None = None,
) -> dict[str, object]:
    return {
        "role": role,
        "template_name": TEMPLATE,
        "variables": VARIABLES,
        "response_model": _Probe,
        "safe_default": _SAFE_DEFAULT,
        "request_id": request_id,
        "settings": settings,
        "sessions": sessions,
        "completion_fn": provider,
        "sleep": lambda _seconds: None,
        "seed": seed,
    }


def _reply(direction: str = "bullish", confidence: float = 0.7) -> CompletionReply:
    return CompletionReply(
        content=f'{{"direction": "{direction}", "confidence": {confidence}}}',
        input_tokens=50,
        output_tokens=10,
        reasoning_tokens=2,
    )


def _all_calls(sessions: sessionmaker[Session]) -> list[LLMCall]:
    with sessions() as session:
        return list(session.execute(select(LLMCall)).scalars().all())


# --- AC-1: role routing -----------------------------------------------------


def test_role_routes_to_configured_model_and_effort(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    small_provider = FakeProvider([_reply()])
    result = call_llm(**_kwargs(settings, sessions, small_provider, role=Role.SMALL))  # type: ignore[arg-type]
    assert not result.flagged
    request = small_provider.requests[0]
    assert request.model == settings.llm_small_model
    assert request.reasoning_effort == settings.llm_reasoning_effort_small
    assert request.max_tokens == settings.llm_output_allowance_tokens

    large_provider = FakeProvider([_reply()])
    call_llm(**_kwargs(settings, sessions, large_provider, role=Role.LARGE))  # type: ignore[arg-type]
    large_request = large_provider.requests[0]
    assert large_request.model == settings.llm_large_model
    assert large_request.reasoning_effort == settings.llm_reasoning_effort_large


# --- AC-2: response cache ----------------------------------------------------


def test_model_id_with_a_colon_is_cached(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    """OpenRouter's free routes end in ":free", which Windows rejects in a path."""
    settings = settings.model_copy(update={"llm_small_model": "qwen/qwen3.8-27b:free"})
    provider = FakeProvider([_reply()])
    kwargs = _kwargs(settings, sessions, provider)

    call_llm(**kwargs)  # type: ignore[arg-type]
    second = call_llm(**kwargs)  # type: ignore[arg-type]

    assert second.cache_hit
    assert len(provider.requests) == 1


def test_repeated_call_is_cached_and_seed_change_forces_new_call(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    provider = FakeProvider([_reply()])
    kwargs = _kwargs(settings, sessions, provider)

    first = call_llm(**kwargs)  # type: ignore[arg-type]
    second = call_llm(**kwargs)  # type: ignore[arg-type]

    assert not first.cache_hit
    assert second.cache_hit
    assert second.input_tokens == 0
    assert second.output_tokens == 0
    assert len(provider.requests) == 1  # provider called only once

    rows = _all_calls(sessions)
    assert len(rows) == 2
    assert rows[0].cache_hit is False
    assert rows[1].cache_hit is True

    other_provider = FakeProvider([_reply(direction="bearish")])
    third = call_llm(**_kwargs(settings, sessions, other_provider, seed=999))  # type: ignore[arg-type]
    assert not third.cache_hit
    assert len(other_provider.requests) == 1


def test_cache_hit_served_even_when_daily_budget_is_exhausted(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    provider = FakeProvider([_reply()])
    kwargs = _kwargs(settings, sessions, provider)
    call_llm(**kwargs)  # type: ignore[arg-type]  # primes the cache

    with sessions() as session:
        session.add(
            LLMCall(
                request_id="prior",
                role="small",
                model=settings.llm_small_model,
                prompt_version="deadbeef0000",
                cache_hit=False,
                cache_key="unrelated",
                input_tokens=settings.llm_daily_token_budget,
                output_tokens=0,
                reasoning_tokens=0,
                latency_ms=0,
                flagged=False,
                created_at=utc_now(),
            )
        )
        session.commit()

    result = call_llm(**kwargs)  # type: ignore[arg-type]
    assert result.cache_hit


# --- AC-3: retries and backoff ----------------------------------------------


def test_429_retried_with_backoff_then_succeeds(
    settings: Settings, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("bullpit.llm.gateway.random.uniform", lambda _a, _b: 0.0)
    provider = FakeProvider([RateLimited("429"), RateLimited("429"), _reply()])
    waits: list[float] = []
    kwargs = _kwargs(settings, sessions, provider)
    kwargs["sleep"] = waits.append

    result = call_llm(**kwargs)  # type: ignore[arg-type]

    assert not result.flagged
    assert len(waits) == 2
    assert waits[1] > waits[0]
    assert len(provider.requests) == 3


@pytest.mark.parametrize(
    ("failure", "raised"),
    [(RateLimited("429"), QuotaExhausted), (ProviderTransient("timeout"), LLMUnavailable)],
)
def test_failure_on_every_attempt_raises_after_retries(
    settings: Settings,
    sessions: sessionmaker[Session],
    failure: Exception,
    raised: type[BullPitError],
) -> None:
    provider = FakeProvider([failure] * (settings.llm_max_retries + 1))
    with pytest.raises(raised):
        call_llm(**_kwargs(settings, sessions, provider))  # type: ignore[arg-type]
    assert len(provider.requests) == settings.llm_max_retries + 1
    assert _all_calls(sessions) == []


# --- AC-4: validation retry and flagged fallback ----------------------------


def test_invalid_json_then_valid_retries_once_with_error_included(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    bad = CompletionReply(content="not json", input_tokens=10, output_tokens=5, reasoning_tokens=1)
    good = _reply()
    provider = FakeProvider([bad, good])

    result = call_llm(**_kwargs(settings, sessions, provider))  # type: ignore[arg-type]

    assert not result.flagged
    assert result.value.direction == "bullish"
    assert result.input_tokens == bad.input_tokens + good.input_tokens
    assert result.output_tokens == bad.output_tokens + good.output_tokens
    assert result.reasoning_tokens == bad.reasoning_tokens + good.reasoning_tokens
    assert len(provider.requests) == 2
    retry_messages = provider.requests[1].messages
    assert "failed validation" in retry_messages[-1]["content"]


def test_invalid_twice_returns_safe_default_flagged_and_caches_nothing(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    empty = CompletionReply(content="", input_tokens=8, output_tokens=0, reasoning_tokens=3)
    bad = CompletionReply(content="not json", input_tokens=10, output_tokens=5, reasoning_tokens=1)
    provider = FakeProvider([empty, bad])

    result = call_llm(**_kwargs(settings, sessions, provider))  # type: ignore[arg-type]

    assert result.flagged
    assert result.value == _SAFE_DEFAULT
    assert result.input_tokens == bad.input_tokens + empty.input_tokens
    assert result.output_tokens == bad.output_tokens + empty.output_tokens
    assert result.reasoning_tokens == bad.reasoning_tokens + empty.reasoning_tokens
    # An empty (e.g. provider-rejected) first reply isn't replayed as an empty assistant turn.
    assert all(message["content"] for message in provider.requests[1].messages)

    # Nothing was cached: an identical call is still a miss and calls the provider.
    fresh_provider = FakeProvider([_reply()])
    second = call_llm(**_kwargs(settings, sessions, fresh_provider))  # type: ignore[arg-type]
    assert not second.cache_hit
    assert len(fresh_provider.requests) == 1


# --- AC-5: every completed call writes exactly one row ----------------------


def test_hit_success_and_flagged_fallback_each_write_one_row(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    success_provider = FakeProvider([_reply()])
    call_llm(**_kwargs(settings, sessions, success_provider, request_id="r-success"))  # type: ignore[arg-type]
    call_llm(**_kwargs(settings, sessions, success_provider, request_id="r-hit"))  # type: ignore[arg-type]

    flagged_provider = FakeProvider(
        [
            CompletionReply(content="x", input_tokens=1, output_tokens=1, reasoning_tokens=0),
            CompletionReply(content="x", input_tokens=1, output_tokens=1, reasoning_tokens=0),
        ]
    )
    call_llm(**_kwargs(settings, sessions, flagged_provider, seed=42, request_id="r-flagged"))  # type: ignore[arg-type]

    rows = _all_calls(sessions)
    assert len(rows) == 3
    assert sorted(r.request_id for r in rows) == ["r-flagged", "r-hit", "r-success"]


# --- AC-6: daily budget ------------------------------------------------------


def test_daily_budget_exceeded_raises_before_network_call(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        session.add(
            LLMCall(
                request_id="prior",
                role="small",
                model=settings.llm_small_model,
                prompt_version="deadbeef0000",
                cache_hit=False,
                cache_key="unrelated",
                input_tokens=settings.llm_daily_token_budget,
                output_tokens=0,
                reasoning_tokens=0,
                latency_ms=0,
                flagged=False,
                created_at=utc_now(),
            )
        )
        session.commit()

    provider = FakeProvider([])
    with pytest.raises(QuotaExhausted):
        call_llm(**_kwargs(settings, sessions, provider))  # type: ignore[arg-type]
    assert provider.requests == []


def test_daily_budget_ignores_rows_older_than_24h(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        session.add(
            LLMCall(
                request_id="old",
                role="small",
                model=settings.llm_small_model,
                prompt_version="deadbeef0000",
                cache_hit=False,
                cache_key="unrelated",
                input_tokens=settings.llm_daily_token_budget,
                output_tokens=0,
                reasoning_tokens=0,
                latency_ms=0,
                flagged=False,
                created_at=utc_now() - timedelta(hours=25),
            )
        )
        session.commit()

    provider = FakeProvider([_reply()])
    result = call_llm(**_kwargs(settings, sessions, provider))  # type: ignore[arg-type]
    assert not result.flagged
    assert len(provider.requests) == 1


# --- AC-8: per-call ceiling ---------------------------------------------------


def test_oversized_prompt_raises_before_network_call(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    huge_variables = {"ticker": "AAPL", "indicators": {"HUGE": "x" * 30_000}}
    provider = FakeProvider([])
    kwargs = _kwargs(settings, sessions, provider)
    kwargs["variables"] = huge_variables

    with pytest.raises(PromptTooLarge, match=TEMPLATE):
        call_llm(**kwargs)  # type: ignore[arg-type]
    assert provider.requests == []


# --- The LiteLLM adapter: no LiteLLM exception leaves it (specs-plan sec12) ---

_MODEL = "openai/gpt-oss-20b"


def _request() -> CompletionRequest:
    return CompletionRequest(
        model=_MODEL,
        messages=[{"role": "user", "content": "x" * 400}],
        temperature=0.0,
        seed=1,
        reasoning_effort="low",
        max_tokens=2000,
    )


@pytest.mark.parametrize(
    ("provider_error", "raised"),
    [
        (ServiceUnavailableError("overloaded", "groq", _MODEL), ProviderTransient),
        (AuthenticationError("invalid api key", "groq", _MODEL), LLMUnavailable),
        (BadRequestError("bad request", _MODEL, "groq"), LLMUnavailable),
    ],
)
def test_provider_errors_are_mapped(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: Exception,
    raised: type[Exception],
) -> None:
    def fail(**_kwargs: object) -> None:
        raise provider_error

    monkeypatch.setattr("bullpit.llm.gateway.get_settings", lambda: settings)
    monkeypatch.setattr("bullpit.llm.gateway.litellm.completion", fail)
    with pytest.raises(raised):
        litellm_completion(_request())


def test_json_rejected_by_provider_is_an_empty_reply_charged_worst_case(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: dict[str, object] = {}

    def reject(**kwargs: object) -> None:
        sent.update(kwargs)
        raise BadRequestError(
            'GroqException - {"error":{"code":"json_validate_failed"}}', _MODEL, "groq"
        )

    monkeypatch.setattr("bullpit.llm.gateway.get_settings", lambda: settings)
    monkeypatch.setattr("bullpit.llm.gateway.litellm.completion", reject)

    reply = litellm_completion(_request())

    assert reply.content == ""
    assert reply.input_tokens == 100  # 400 characters at 4 per token
    assert reply.output_tokens == 2000  # the whole output cap
    assert sent["timeout"] == settings.llm_timeout_seconds


def test_openrouter_route(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def fake_completion(**kwargs: object) -> SimpleNamespace:
        sent.update(kwargs)
        message = SimpleNamespace(content='{"direction": "up", "confidence": 0.5}')
        usage = SimpleNamespace(
            prompt_tokens=10, completion_tokens=8, completion_tokens_details=None
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    routed = settings.model_copy(
        update={"llm_provider": "openrouter", "openrouter_api_key": SecretStr("or-key")}
    )
    monkeypatch.setattr("bullpit.llm.gateway.get_settings", lambda: routed)
    monkeypatch.setattr("bullpit.llm.gateway.litellm.completion", fake_completion)

    reply = litellm_completion(_request())

    assert sent["model"] == f"openrouter/{_MODEL}"
    assert sent["api_key"] == "or-key"
    assert "seed" not in sent
    assert "response_format" not in sent
    assert reply.input_tokens == 10
