"""structlog setup: readable console output, JSON lines in a rotating file.

Called once, from the CLI entry point. Every log line carries `request_id`,
`mode` and `as_of` once they're bound with `structlog.contextvars.bind_contextvars`
(dev-plan.md sec6.3). Secret values are always redacted, on both outputs.
"""

from __future__ import annotations

import logging
import logging.handlers
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

from bullpit.config import Settings

_LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_LOG_FILE_BACKUP_COUNT = 3

_SECRET_KEY_MARKERS = ("key", "secret", "token", "password", "authorization")
_REDACTED = "***"

# Third-party libraries that log at INFO by default and would otherwise drown
# out our own structured lines (e.g. httpx logs "HTTP Request: ..." for every
# call, which would break `doctor`'s one-line-per-check contract).
_QUIET_THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "urllib3")


def _secret_values(settings: Settings) -> set[str]:
    """Every real secret value currently configured, so it can be masked
    verbatim wherever it appears in a log line (not just under a
    secret-looking field name).
    """
    values: set[str] = set()
    for field in ("alpaca_api_key", "alpaca_secret_key", "groq_api_key"):
        secret = getattr(settings, field)
        if secret is not None:
            values.add(secret.get_secret_value())
    return values


def make_redactor(settings: Settings) -> structlog.types.Processor:
    """Build a structlog processor that masks secrets in an event dict.

    Masks (a) the exact configured secret values wherever they appear, and
    (b) the value of any key whose name looks like it holds a secret.
    """
    literal_values = _secret_values(settings)

    def redact_secrets(
        _logger: object, _method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        for key, value in list(event_dict.items()):
            lower_key = key.lower()
            if any(marker in lower_key for marker in _SECRET_KEY_MARKERS):
                event_dict[key] = _REDACTED
                continue
            if isinstance(value, str):
                redacted = value
                for secret_value in literal_values:
                    if secret_value and secret_value in redacted:
                        redacted = redacted.replace(secret_value, _REDACTED)
                event_dict[key] = redacted
        return event_dict

    return cast(structlog.types.Processor, redact_secrets)


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the stdlib logging handlers it renders through.

    Idempotent: safe to call more than once (later calls replace the handlers).
    """
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
        )
    )

    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_dir / "bullpit.log",
        maxBytes=_LOG_FILE_MAX_BYTES,
        backupCount=_LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers = [console_handler, file_handler]
    root_logger.setLevel(settings.log_level)

    for name in _QUIET_THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            make_redactor(settings),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(*args: Any, **kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Thin wrapper so callers don't need to import structlog directly."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(*args, **kwargs))
