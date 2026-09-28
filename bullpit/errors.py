"""The domain exception hierarchy.

Every exception bullpit code raises across a module boundary is one of these
(dev-plan.md sec2.2). Third-party exceptions are caught and wrapped at the
edge (bullpit/broker, bullpit/data, bullpit/llm), never left to leak through.

Only ConfigError and LiveTradingRefused have behaviour in M0. The rest are
declared now so the hierarchy is fixed in one place; later milestones raise
them without changing this file.
"""

from __future__ import annotations


class BullPitError(Exception):
    """Base class for every exception bullpit code raises on purpose."""


class ConfigError(BullPitError):
    """A required setting is missing or invalid.

    Always names the *variable*, never its value.
    """


class LiveTradingRefused(BullPitError):
    """The paper-only guard refused to build a trading client.

    See bullpit/broker/safety.py. There is no setting that disables this.
    """


class DataUnavailable(BullPitError):
    """A data source has no usable data for the request (used from M1)."""


class LookaheadViolation(BullPitError):
    """Data dated after `as_of` would have reached an agent (used from M1)."""


class QuotaExhausted(BullPitError):
    """The LLM gateway's daily token budget for a model is used up (used from M2)."""


class ValidationFailed(BullPitError):
    """An LLM reply failed schema validation after its retry (used from M2)."""


class PromptTooLarge(BullPitError):
    """A rendered prompt's estimated size exceeds the per-minute token limit
    (used from M2). Raised before any network call.
    """


class LLMUnavailable(BullPitError):
    """The LLM provider can't serve the call: it kept failing transiently
    through every retry, or rejected the request outright (e.g. a bad key)
    (used from M2).
    """


class BrokerRejected(BullPitError):
    """A broker rejected an order or a request about one (used from M3/M8)."""
