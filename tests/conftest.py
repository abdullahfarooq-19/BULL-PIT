"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.journal.db import make_engine, make_sessions
from bullpit.journal.models import Base
from bullpit.llm.gateway import reset_langfuse_registration, reset_token_buckets


def fixture_path(*parts: str) -> Path:
    """Path to a file under tests/fixtures/, e.g. fixture_path("prices", "aapl_yf.parquet")."""
    return Path(__file__).parent / "fixtures" / Path(*parts)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """A Settings object with a temp cache dir, fake keys and no .env file."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_cache_dir=tmp_path / "data_cache",
        alpaca_api_key="fake-key",
        alpaca_secret_key="fake-secret",
        groq_api_key="fake-groq-key",
        sec_contact_email="test@example.com",
    )


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    """A file-backed journal (not `sqlite://`: an in-memory database is one
    per connection, so a worker thread -- the parallel analysts, M3 NFR-2 --
    would see an empty journal). Schema created directly; Alembic is checked
    by hand (M2 sec9.5)."""
    engine = make_engine(f"sqlite:///{tmp_path / 'journal.db'}")
    Base.metadata.create_all(engine)
    return make_sessions(engine)


@pytest.fixture(autouse=True)
def _reset_llm_gateway_module_state() -> Iterator[None]:
    """The token buckets and the Langfuse registration latch are module-level
    (D-M2-3: pacing is per process), so tests must not leak state between runs.
    """
    reset_token_buckets()
    reset_langfuse_registration()
    yield
    reset_token_buckets()
    reset_langfuse_registration()
