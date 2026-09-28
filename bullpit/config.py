"""Typed application settings, loaded from `.env` and the environment.

One `Settings` object is the single source of truth for every tunable value
(CLAUDE.md: "no magic numbers"). M0 only defines the fields M0 code reads;
each later milestone adds the settings it needs, with the architecture's
default value (dev-plan.md D-M0-12).
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bullpit.broker.safety import assert_paper_url
from bullpit.errors import ConfigError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _empty_to_none(value: object) -> object:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class Settings(BaseSettings):
    """All configuration Bull Pit needs, typed and validated at load time."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Alpaca paper trading -------------------------------------------
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None

    # --- Groq / LiteLLM ---------------------------------------------------
    groq_api_key: SecretStr | None = None
    llm_small_model: str = "openai/gpt-oss-20b"
    llm_large_model: str = "openai/gpt-oss-120b"

    # --- SEC EDGAR -----------------------------------------------------
    sec_contact_email: str | None = None
    sec_max_requests_per_second: float = 10.0

    # --- Data layer -------------------------------------------------------
    data_cache_dir: Path = Path("data_cache")
    news_lookback_days: int = 7

    # --- Request check and analysts (M3) -----------------------------------
    min_price_sessions: int = 60
    price_history_sessions: int = 300
    news_max_headlines: int = 15
    news_duplicate_similarity: float = 0.8
    news_thin_articles: int = 3
    sentiment_neutral_band: float = 0.15
    brain_min_abs_score: float = 0.15
    brain_conflict_min_confidence: float = 0.4
    request_lock_timeout_minutes: int = 30
    llm_small_model_cutoff: date = date(2024, 6, 30)
    llm_large_model_cutoff: date = date(2024, 6, 30)

    # --- LLM gateway (M2) -------------------------------------------------
    llm_reasoning_effort_small: str = "low"
    llm_reasoning_effort_large: str = "low"
    llm_rpm_limit: int = 30
    llm_tpm_limit: int = 8000
    llm_output_allowance_tokens: int = 1869
    llm_daily_token_budget: int = 200_000
    llm_max_retries: int = 5
    llm_backoff_base_seconds: float = 1.0
    llm_timeout_seconds: float = 60.0
    llm_seed: int = 1

    # --- Journal (M2) -------------------------------------------------------
    journal_db_path: Path = Path("journal.db")

    # --- Langfuse (optional, off by default; M2 D7) -----------------------
    langfuse_enabled: bool = False
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None

    # --- Logging ------------------------------------------------------------
    log_level: str = "INFO"
    log_dir: Path = Path("logs")

    # --- Misc -----------------------------------------------------------
    http_timeout_seconds: float = 10.0

    @field_validator(
        "alpaca_api_key",
        "alpaca_secret_key",
        "groq_api_key",
        "sec_contact_email",
        "langfuse_public_key",
        "langfuse_secret_key",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        return _empty_to_none(value)

    @field_validator("alpaca_base_url")
    @classmethod
    def _must_be_paper(cls, value: str) -> str:
        return assert_paper_url(value)

    @field_validator("sec_contact_email")
    @classmethod
    def _looks_like_email(cls, value: str | None) -> str | None:
        if value is not None and not _EMAIL_RE.match(value):
            raise ConfigError(f"SEC_CONTACT_EMAIL does not look like an email address: {value!r}")
        return value

    def missing_secrets(self) -> list[str]:
        """Names of required secrets that are unset, in a fixed order."""
        required: list[tuple[str, object]] = [
            ("ALPACA_API_KEY", self.alpaca_api_key),
            ("ALPACA_SECRET_KEY", self.alpaca_secret_key),
            ("GROQ_API_KEY", self.groq_api_key),
            ("SEC_CONTACT_EMAIL", self.sec_contact_email),
        ]
        return [name for name, value in required if value is None]

    def require(self, name: str) -> str:
        """Return the plain value of a secret field, or raise ConfigError.

        `name` is the environment variable name (e.g. "ALPACA_API_KEY").
        """
        field_map: dict[str, SecretStr | str | None] = {
            "ALPACA_API_KEY": self.alpaca_api_key,
            "ALPACA_SECRET_KEY": self.alpaca_secret_key,
            "GROQ_API_KEY": self.groq_api_key,
            "SEC_CONTACT_EMAIL": self.sec_contact_email,
        }
        if name not in field_map:
            raise ConfigError(f"Unknown setting: {name}")
        value = field_map[name]
        if value is None:
            raise ConfigError(f"{name} is not set. Add it to your .env file.")
        return value.get_secret_value() if isinstance(value, SecretStr) else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor for normal use.

    Tests should build `Settings(...)` directly with explicit values and
    `_env_file=None`, so a developer's own `.env` never leaks into a test.
    """
    return Settings()
