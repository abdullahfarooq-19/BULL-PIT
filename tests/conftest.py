"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from bullpit.config import Settings


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
