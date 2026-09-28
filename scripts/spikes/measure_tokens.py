"""M2 spike: measure real token usage (including reasoning) for one
representative analyst-sized prompt against both pinned models
(M2 specs-plan sec9.6, AC-7).

Spends real Groq quota: exactly one call per pinned model, well under the
per-call ceiling and the daily budget (NFR-3). The journal and the response
cache both live in a throwaway temp directory, so every run is a real call.
Exits non-zero if either call is flagged or its real total is above
`llm_tpm_limit`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from _common import section
from _common import settings as base_settings
from pydantic import BaseModel

from bullpit.journal.db import journal_url, make_engine, make_sessions
from bullpit.journal.models import Base
from bullpit.llm.gateway import Role, call_llm


class _Probe(BaseModel):
    direction: str
    confidence: float


_SAFE_DEFAULT = _Probe(direction="neutral", confidence=0.0)

_VARIABLES = {
    "ticker": "AAPL",
    "indicators": {
        "RSI14": 58.3,
        "SMA50_gt_SMA200": True,
        "MACD_hist": 0.42,
        "ATR14_pct": 1.8,
        "volume_vs_avg_20d": 1.3,
    },
}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = base_settings().model_copy(
            update={
                "journal_db_path": tmp_path / "journal.db",
                "data_cache_dir": tmp_path / "data_cache",
            }
        )
        if settings.groq_api_key is None:
            print("GROQ_API_KEY is not set. Aborting.")
            raise SystemExit(1)

        engine = make_engine(journal_url(settings))
        Base.metadata.create_all(engine)
        sessions = make_sessions(engine)

        problem = False
        for role in (Role.SMALL, Role.LARGE):
            model = settings.llm_small_model if role is Role.SMALL else settings.llm_large_model
            section(f"{role.value}: {model}")
            result = call_llm(
                role,
                "measurement_probe.md",
                _VARIABLES,
                _Probe,
                safe_default=_SAFE_DEFAULT,
                request_id=f"measure-{role.value}",
                settings=settings,
                sessions=sessions,
                seed=settings.llm_seed,
            )
            total = result.input_tokens + result.output_tokens + result.reasoning_tokens
            print(
                f"  input={result.input_tokens} output={result.output_tokens} "
                f"reasoning={result.reasoning_tokens} total={total} "
                f"latency_ms={result.latency_ms} flagged={result.flagged}"
            )
            if result.flagged:
                print(f"  WARNING: {role.value} reply was flagged (validation failed twice)")
                problem = True
            if total > settings.llm_tpm_limit:
                print(f"  WARNING: total {total} exceeds llm_tpm_limit {settings.llm_tpm_limit}")
                problem = True

        engine.dispose()  # release SQLite handles before the temp dir is removed (Windows)

        if problem:
            raise SystemExit(1)
        print("\nDone. Both calls within llm_tpm_limit and not flagged.")


if __name__ == "__main__":
    main()
