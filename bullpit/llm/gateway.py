"""The one controlled door for every LLM call (architecture Part 3; M2
specs-plan sec5.2, sec9.2): routed to the pinned model, cached, rate-limited,
budget-tracked, and validated into typed replies.

`call_llm` runs, in order: render -> ceiling check -> cache lookup ->
daily-budget check -> pace -> call (with backoff) -> validate (one retry) ->
record. It never raises for an invalid reply (returns `safe_default`,
`flagged=True`); it raises `PromptTooLarge` or `QuotaExhausted` before any
network call, and `QuotaExhausted` or `LLMUnavailable` if retries run out.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import litellm
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from litellm.exceptions import (
    APIConnectionError,
    BadGatewayError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from bullpit.clock import utc_now
from bullpit.config import Settings, get_settings
from bullpit.errors import ConfigError, LLMUnavailable, PromptTooLarge, QuotaExhausted
from bullpit.journal.models import LLMCall
from bullpit.logging import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_CHARS_PER_TOKEN = 4
_BUCKET_WINDOW_SECONDS = 60.0
# Groq validates JSON mode server-side and rejects a generation that isn't a
# JSON object (including one cut off by `max_tokens`) with this error code.
_GROQ_JSON_REJECTED = "json_validate_failed"

# autoescape is for HTML/XML output; these templates render plain-text LLM
# prompts, so escaping would corrupt them.
_jinja_env = Environment(  # noqa: S701
    loader=FileSystemLoader(_PROMPTS_DIR), undefined=StrictUndefined
)


class Role(StrEnum):
    SMALL = "small"
    LARGE = "large"


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    value: T
    flagged: bool
    cache_hit: bool
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: list[dict[str, str]]
    temperature: float
    seed: int
    reasoning_effort: str
    max_tokens: int


@dataclass(frozen=True)
class CompletionReply:
    content: str
    input_tokens: int
    output_tokens: int  # visible output only
    reasoning_tokens: int


class CompletionFn(Protocol):
    def __call__(self, request: CompletionRequest) -> CompletionReply: ...


class RateLimited(Exception):
    """Gateway-internal: the provider returned a 429."""


class ProviderTransient(Exception):
    """Gateway-internal: a timeout or connection error."""


# --- Template rendering (M2-FR-3) ------------------------------------------


def _render(template_name: str, variables: Mapping[str, object]) -> tuple[str, str]:
    content = (_PROMPTS_DIR / template_name).read_bytes()
    version = hashlib.sha256(content).hexdigest()[:12]
    rendered = _jinja_env.get_template(template_name).render(**variables)
    return rendered, version


def _prompt_tokens(text: str) -> int:
    """D-M2-2: a length heuristic, not a real tokenizer; errs high on purpose."""
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def _estimate_tokens(rendered_prompt: str, settings: Settings) -> int:
    return _prompt_tokens(rendered_prompt) + settings.llm_output_allowance_tokens


def _model_for(role: Role, settings: Settings) -> str:
    return settings.llm_small_model if role is Role.SMALL else settings.llm_large_model


def _reasoning_effort_for(role: Role, settings: Settings) -> str:
    return (
        settings.llm_reasoning_effort_small
        if role is Role.SMALL
        else settings.llm_reasoning_effort_large
    )


# --- Response cache (M2-FR-5, FR-6; ADR-0004) -------------------------------


def _cache_key(
    model: str,
    rendered_prompt: str,
    temperature: float,
    seed: int,
    prompt_version: str,
    reasoning_effort: str,
) -> str:
    payload = "\x1f".join(
        [model, rendered_prompt, repr(temperature), str(seed), prompt_version, reasoning_effort]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_path(settings: Settings, model: str, cache_key: str) -> Path:
    slug = model.replace("/", "_")
    return settings.data_cache_dir / "llm" / slug / f"{cache_key}.json"


def _load_cache[T: BaseModel](path: Path, response_model: type[T]) -> T | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return response_model.model_validate(payload["value"])
    except (json.JSONDecodeError, KeyError, ValidationError):
        # A stale or corrupted entry is a miss, not an error (ADR-0004).
        return None


def _save_cache(
    path: Path, value: BaseModel, *, input_tokens: int, output_tokens: int, reasoning_tokens: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "value": value.model_dump(mode="json"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    tmp_path.replace(path)  # atomic, same pattern as bullpit/data/cache.py


# --- Daily budget (M2-FR-9; D-M2-3) -----------------------------------------


def _usage_last_24h(sessions: sessionmaker[Session], model: str) -> int:
    cutoff = utc_now() - timedelta(hours=24)
    stmt = select(
        func.coalesce(
            func.sum(LLMCall.input_tokens + LLMCall.output_tokens + LLMCall.reasoning_tokens), 0
        )
    ).where(LLMCall.model == model, LLMCall.cache_hit.is_(False), LLMCall.created_at >= cutoff)
    with sessions() as session:
        return session.execute(stmt).scalar_one()


# --- Per-model token bucket (M2-FR-8; D-M2-3: in-memory, per process) -------


class _TokenBucket:
    def __init__(self, rpm_limit: int, tpm_limit: int) -> None:
        self._rpm_limit = rpm_limit
        self._tpm_limit = tpm_limit
        self._request_times: list[float] = []
        self._token_events: list[tuple[float, int]] = []

    def acquire(self, tokens: int, *, sleep: Callable[[float], None]) -> None:
        while True:
            now = time.monotonic()
            cutoff = now - _BUCKET_WINDOW_SECONDS
            self._request_times = [t for t in self._request_times if t >= cutoff]
            self._token_events = [(t, n) for t, n in self._token_events if t >= cutoff]
            tokens_used = sum(n for _, n in self._token_events)
            under_rpm = len(self._request_times) < self._rpm_limit
            under_tpm = tokens_used + tokens <= self._tpm_limit
            if under_rpm and under_tpm:
                self._request_times.append(now)
                self._token_events.append((now, tokens))
                return
            sleep(1.0)


_token_buckets: dict[str, _TokenBucket] = {}


def _bucket_for(model: str, settings: Settings) -> _TokenBucket:
    bucket = _token_buckets.get(model)
    if bucket is None:
        bucket = _TokenBucket(settings.llm_rpm_limit, settings.llm_tpm_limit)
        _token_buckets[model] = bucket
    return bucket


def reset_token_buckets() -> None:
    """Test-only: pacing is per process (D-M2-3), so tests reset it between runs."""
    _token_buckets.clear()


# --- Backoff (M2-FR-7; sec11.3) ---------------------------------------------


def _call_with_backoff(
    completion_fn: CompletionFn,
    request: CompletionRequest,
    *,
    settings: Settings,
    sleep: Callable[[float], None],
) -> CompletionReply:
    attempt = 0
    while True:
        try:
            return completion_fn(request)
        except (RateLimited, ProviderTransient) as exc:
            if attempt == settings.llm_max_retries:
                if isinstance(exc, RateLimited):
                    raise QuotaExhausted(
                        f"{request.model}: still rate-limited after "
                        f"{settings.llm_max_retries} retries"
                    ) from exc
                raise LLMUnavailable(
                    f"{request.model}: still unavailable after {settings.llm_max_retries} retries"
                ) from exc
            wait = settings.llm_backoff_base_seconds * (2**attempt) + random.uniform(  # noqa: S311
                0, settings.llm_backoff_base_seconds
            )
            sleep(wait)
            attempt += 1


# --- Structured-output validation (M2-FR-10) --------------------------------


def _validate[T: BaseModel](content: str, response_model: type[T]) -> tuple[T | None, str | None]:
    """Returns `(value, error)`; `value` is `None` iff `error` is set."""
    if not content:
        return None, "the reply was empty or was not a JSON object"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    try:
        return response_model.model_validate(payload), None
    except ValidationError as exc:
        return None, f"schema validation failed: {exc}"


@dataclass(frozen=True)
class _Validated[T: BaseModel]:
    value: T
    flagged: bool
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int


def _validate_with_retry[T: BaseModel](
    completion_fn: CompletionFn,
    request: CompletionRequest,
    first_reply: CompletionReply,
    response_model: type[T],
    *,
    safe_default: T,
    settings: Settings,
    sleep: Callable[[float], None],
) -> _Validated[T]:
    total_input = first_reply.input_tokens
    total_output = first_reply.output_tokens
    total_reasoning = first_reply.reasoning_tokens

    value, error = _validate(first_reply.content, response_model)
    if value is not None:
        return _Validated(value, False, total_input, total_output, total_reasoning)

    # A provider-rejected generation has no content to replay, and an empty
    # assistant turn isn't a valid message.
    previous_reply = (
        [{"role": "assistant", "content": first_reply.content}] if first_reply.content else []
    )
    retry_request = replace(
        request,
        messages=[
            *request.messages,
            *previous_reply,
            {
                "role": "user",
                "content": (
                    f"Your last reply failed validation ({error}). Reply again with a single "
                    "JSON object matching the required schema, and nothing else."
                ),
            },
        ],
    )
    retry_reply = _call_with_backoff(completion_fn, retry_request, settings=settings, sleep=sleep)
    total_input += retry_reply.input_tokens
    total_output += retry_reply.output_tokens
    total_reasoning += retry_reply.reasoning_tokens

    value, _error = _validate(retry_reply.content, response_model)
    if value is not None:
        return _Validated(value, False, total_input, total_output, total_reasoning)

    return _Validated(safe_default, True, total_input, total_output, total_reasoning)


# --- Journal recording (M2-FR-11, FR-11a) -----------------------------------


def _record(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    role: Role,
    model: str,
    prompt_version: str,
    cache_hit: bool,
    cache_key: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    latency_ms: int,
    flagged: bool,
) -> None:
    with sessions() as session:
        session.add(
            LLMCall(
                request_id=request_id,
                role=role.value,
                model=model,
                prompt_version=prompt_version,
                cache_hit=cache_hit,
                cache_key=cache_key,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                latency_ms=latency_ms,
                flagged=flagged,
                created_at=utc_now(),
            )
        )
        session.commit()


# --- Langfuse (optional; M2-FR-14, D7) --------------------------------------

_langfuse_registered = False


def _maybe_register_langfuse(settings: Settings) -> None:
    global _langfuse_registered
    if _langfuse_registered or not settings.langfuse_enabled:
        return
    public_key, secret_key = settings.langfuse_public_key, settings.langfuse_secret_key
    if public_key is None or secret_key is None:
        missing = [
            name
            for name, value in (
                ("LANGFUSE_PUBLIC_KEY", public_key),
                ("LANGFUSE_SECRET_KEY", secret_key),
            )
            if value is None
        ]
        raise ConfigError(f"LANGFUSE_ENABLED is true but these are not set: {', '.join(missing)}")
    try:
        import langfuse  # noqa: F401
    except ImportError as exc:
        raise ConfigError(
            "LANGFUSE_ENABLED is true but the `langfuse` package isn't installed "
            "(it's not a project dependency, D-M2-9). Run `uv add langfuse` to enable tracing."
        ) from exc
    os.environ["LANGFUSE_PUBLIC_KEY"] = public_key.get_secret_value()
    os.environ["LANGFUSE_SECRET_KEY"] = secret_key.get_secret_value()
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host
    litellm.success_callback.append("langfuse")
    litellm.failure_callback.append("langfuse")
    _langfuse_registered = True


def reset_langfuse_registration() -> None:
    """Test-only: registration is a module-level latch, guarded by a fixture."""
    global _langfuse_registered
    _langfuse_registered = False


# --- The real provider (the only code that touches LiteLLM) ----------------


def litellm_completion(request: CompletionRequest) -> CompletionReply:
    """Call Groq through LiteLLM; no LiteLLM exception leaves this function.

    429 -> `RateLimited`; timeout, connection error, 500/502/503 ->
    `ProviderTransient` (both retried by the caller). A JSON-mode generation
    Groq rejects comes back as an empty reply, which the gateway treats as
    an invalid reply (FR-10). Any other provider error -> `LLMUnavailable`,
    not retried.
    """
    settings = get_settings()
    api_key = settings.require("GROQ_API_KEY")
    try:
        response = litellm.completion(
            model=f"groq/{request.model}",
            api_key=api_key,
            messages=request.messages,
            temperature=request.temperature,
            seed=request.seed,
            reasoning_effort=request.reasoning_effort,
            max_tokens=request.max_tokens,
            response_format={"type": "json_object"},
            timeout=settings.llm_timeout_seconds,
        )
    except RateLimitError as exc:
        raise RateLimited(str(exc)) from exc
    except (
        Timeout,
        APIConnectionError,
        InternalServerError,
        BadGatewayError,
        ServiceUnavailableError,
    ) as exc:
        raise ProviderTransient(str(exc)) from exc
    except BadRequestError as exc:
        if _GROQ_JSON_REJECTED not in str(exc):
            raise LLMUnavailable(f"{request.model}: request rejected: {exc}") from exc
        # Groq reports no usage for a rejected generation; charge the worst
        # case so the daily budget can only over-count (sec11.2).
        prompt = "".join(message["content"] for message in request.messages)
        return CompletionReply(
            content="",
            input_tokens=_prompt_tokens(prompt),
            output_tokens=request.max_tokens,
            reasoning_tokens=0,
        )
    except Exception as exc:
        raise LLMUnavailable(f"{request.model}: provider error: {exc}") from exc

    content = response.choices[0].message.content or ""
    usage = response.usage
    details = getattr(usage, "completion_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", None) or 0
    output_tokens = max(usage.completion_tokens - reasoning_tokens, 0)
    return CompletionReply(
        content=content,
        input_tokens=usage.prompt_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


# --- The public entry point --------------------------------------------------


def call_llm[T: BaseModel](
    role: Role,
    template_name: str,
    variables: Mapping[str, object],
    response_model: type[T],
    *,
    safe_default: T,
    request_id: str,
    settings: Settings,
    sessions: sessionmaker[Session],
    seed: int | None = None,
    temperature: float = 0.0,
    completion_fn: CompletionFn = litellm_completion,
    sleep: Callable[[float], None] = time.sleep,
) -> LLMResult[T]:
    """Render, check ceiling, cache, budget, pace, call, validate, log.

    Never raises for an invalid reply (returns `safe_default`, `flagged=True`);
    raises `PromptTooLarge` or `QuotaExhausted` before any network call.
    """
    resolved_seed = settings.llm_seed if seed is None else seed
    model = _model_for(role, settings)
    reasoning_effort = _reasoning_effort_for(role, settings)

    rendered_prompt, prompt_version = _render(template_name, variables)
    estimate = _estimate_tokens(rendered_prompt, settings)
    if estimate > settings.llm_tpm_limit:
        raise PromptTooLarge(
            f"{template_name} (version {prompt_version}): estimated {estimate} tokens "
            f"exceeds the per-minute limit of {settings.llm_tpm_limit}"
        )

    cache_key = _cache_key(
        model, rendered_prompt, temperature, resolved_seed, prompt_version, reasoning_effort
    )
    cache_path = _cache_path(settings, model, cache_key)
    cached = _load_cache(cache_path, response_model)
    if cached is not None:
        logger.info("llm_cache_hit", role=role.value, model=model, request_id=request_id)
        _record(
            sessions,
            request_id=request_id,
            role=role,
            model=model,
            prompt_version=prompt_version,
            cache_hit=True,
            cache_key=cache_key,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            latency_ms=0,
            flagged=False,
        )
        return LLMResult(
            value=cached,
            flagged=False,
            cache_hit=True,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            latency_ms=0,
        )

    used = _usage_last_24h(sessions, model)
    if used + estimate > settings.llm_daily_token_budget:
        raise QuotaExhausted(
            f"{model}: {used} tokens used in the last 24h, "
            f"budget is {settings.llm_daily_token_budget}"
        )

    _maybe_register_langfuse(settings)

    _bucket_for(model, settings).acquire(estimate, sleep=sleep)

    request = CompletionRequest(
        model=model,
        messages=[{"role": "user", "content": rendered_prompt}],
        temperature=temperature,
        seed=resolved_seed,
        reasoning_effort=reasoning_effort,
        max_tokens=settings.llm_output_allowance_tokens,
    )

    start = time.monotonic()
    first_reply = _call_with_backoff(completion_fn, request, settings=settings, sleep=sleep)
    validated = _validate_with_retry(
        completion_fn,
        request,
        first_reply,
        response_model,
        safe_default=safe_default,
        settings=settings,
        sleep=sleep,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    if not validated.flagged:
        _save_cache(
            cache_path,
            validated.value,
            input_tokens=validated.input_tokens,
            output_tokens=validated.output_tokens,
            reasoning_tokens=validated.reasoning_tokens,
        )

    _record(
        sessions,
        request_id=request_id,
        role=role,
        model=model,
        prompt_version=prompt_version,
        cache_hit=False,
        cache_key=cache_key,
        input_tokens=validated.input_tokens,
        output_tokens=validated.output_tokens,
        reasoning_tokens=validated.reasoning_tokens,
        latency_ms=latency_ms,
        flagged=validated.flagged,
    )

    return LLMResult(
        value=validated.value,
        flagged=validated.flagged,
        cache_hit=False,
        input_tokens=validated.input_tokens,
        output_tokens=validated.output_tokens,
        reasoning_tokens=validated.reasoning_tokens,
        latency_ms=latency_ms,
    )
