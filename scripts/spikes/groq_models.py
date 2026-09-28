"""M0 spike: verify Groq / gpt-oss assumptions A1-A6 (specs-plan.md sec11.2).

Checks, with at most ~12 short calls (NFR-7: under 10K tokens total):
  A1  both pinned models are served
  A2  free-tier rate limits, read from response headers
  A3  JSON mode and JSON-schema strict structured output
  A4  `reasoning_effort` is accepted (low, medium) and changes usage
  A5  reasoning tokens are reported in usage; a small output cap can starve content
  A6  `seed` and `temperature` are accepted

Spends real Groq quota. No assertion failure should be treated as fatal --
every result is recorded either way, and findings.md records the verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
import litellm
from _common import save_json, section, settings


def check_models_served(groq_key: str, wanted: set[str]) -> dict[str, Any]:
    section("A1: models served")
    resp = httpx.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {groq_key}"},
        timeout=15,
    )
    resp.raise_for_status()
    served = {m["id"] for m in resp.json().get("data", [])}
    missing = wanted - served
    result = {"served": sorted(served & wanted), "missing": sorted(missing)}
    print(f"  wanted: {sorted(wanted)}")
    print(f"  served: {result['served']}, missing: {result['missing']}")
    return result


def check_rate_limit_headers(groq_key: str, model: str) -> dict[str, Any]:
    """A2: litellm doesn't surface raw response headers, so this hits the
    Groq (OpenAI-compatible) endpoint directly with httpx to read them.
    """
    section("A2: rate-limit headers (direct httpx call)")
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with just: ok"}],
            "max_tokens": 10,
        },
        timeout=15,
    )
    resp.raise_for_status()
    headers = {k: v for k, v in resp.headers.items() if "ratelimit" in k.lower()}
    print(f"  {headers}")
    return headers


def one_call(
    model: str,
    groq_key: str,
    *,
    label: str,
    reasoning_effort: str | None = None,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    seed: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    print(f"\n  call: {label} (model={model}, reasoning_effort={reasoning_effort})")
    kwargs: dict[str, Any] = {
        "model": f"groq/{model}",
        "api_key": groq_key,
        "messages": [
            {
                "role": "user",
                "content": (
                    'Reply with a JSON object: {"direction": "bullish", "confidence": 0.5}. '
                    "Nothing else."
                ),
            }
        ],
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    if response_format is not None:
        kwargs["response_format"] = response_format
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if seed is not None:
        kwargs["seed"] = seed
    if temperature is not None:
        kwargs["temperature"] = temperature

    try:
        response = litellm.completion(**kwargs)
    except Exception as exc:
        print(f"    ERROR: {type(exc).__name__}: {exc}")
        return {"label": label, "error": f"{type(exc).__name__}: {exc}"}

    message = response.choices[0].message
    usage = response.usage.model_dump() if response.usage else {}

    result = {"label": label, "content": message.content, "usage": usage}
    print(f"    content: {message.content!r}")
    print(f"    usage: {usage}")
    return result


def main() -> None:
    s = settings()
    if s.groq_api_key is None:
        print("GROQ_API_KEY is not set. Aborting.")
        raise SystemExit(1)
    groq_key = s.groq_api_key.get_secret_value()
    small, large = s.llm_small_model, s.llm_large_model

    results: dict[str, Any] = {}
    results["a1_models_served"] = check_models_served(groq_key, {small, large})
    results["a2_rate_limit_headers"] = check_rate_limit_headers(groq_key, small)

    section("A3: JSON mode + JSON schema (strict)")
    json_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "signal",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
                    "confidence": {"type": "number"},
                },
                "required": ["direction", "confidence"],
                "additionalProperties": False,
            },
        },
    }
    results["a3_json_object_small"] = one_call(
        small, groq_key, label="json_object mode", response_format={"type": "json_object"}
    )
    results["a3_json_schema_small"] = one_call(
        small, groq_key, label="json_schema strict mode", response_format=json_schema
    )

    section("A4/A5: reasoning_effort + reasoning-token usage")
    results["a4_low_small"] = one_call(small, groq_key, label="low effort", reasoning_effort="low")
    results["a4_medium_small"] = one_call(
        small, groq_key, label="medium effort", reasoning_effort="medium"
    )
    results["a4_low_large"] = one_call(
        large, groq_key, label="low effort (large)", reasoning_effort="low"
    )

    section("A5: small output cap (reasoning may starve content)")
    results["a5_small_max_tokens"] = one_call(
        small, groq_key, label="max_tokens=5, low effort", reasoning_effort="low", max_tokens=5
    )

    section("A6: seed + temperature")
    results["a6_seed_temperature"] = one_call(
        small, groq_key, label="seed=42, temperature=0", seed=42, temperature=0.0
    )

    save_json("groq_models", results)
    print("\nDone. Check scripts/spikes/output/groq_models.json for the full record.")


if __name__ == "__main__":
    main()
