"""Shared fixtures for the M4 agent node tests (plan sec13): a `RequestState`
that has already passed the signals board, and a scripted completion fake
for the four M4 templates.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal

import pytest

from bullpit.agents.signals_board import build_board
from bullpit.config import Settings
from bullpit.domain import Account
from bullpit.llm.gateway import CompletionReply, CompletionRequest
from bullpit.llm.schemas import Evidence, Signal
from bullpit.state import Bar, PriceSnapshot, RequestState
from bullpit.tools.indicators import Indicators

# Fixed first lines the four M4 templates render with (plan sec9.5), so a
# scripted fake can tell them apart without parsing the whole prompt.
FIRST_LINE_BULL = "You are the bull researcher"
FIRST_LINE_BEAR = "You are the bear researcher"
FIRST_LINE_TRADER = "You are the trader"
FIRST_LINE_RISK_REVIEW = "You are the risk manager"

AS_OF = date(2024, 10, 18)
REFERENCE_PRICE = Decimal("182")
ATR = 4.0


def _technical_signal() -> Signal:
    return Signal(
        ticker="AAPL",
        analyst="technical",
        direction="bullish",
        confidence=0.6,
        evidence=[Evidence(id=f"T{i}", fact=f"Technical fact {i}") for i in range(1, 7)],
    )


def _fundamentals_signal() -> Signal:
    return Signal(
        ticker="AAPL",
        analyst="fundamentals",
        direction="neutral",
        confidence=0.4,
        evidence=[Evidence(id=f"F{i}", fact=f"Fundamentals fact {i}") for i in range(1, 6)],
    )


def _sentiment_signal() -> Signal:
    return Signal(
        ticker="AAPL",
        analyst="sentiment",
        direction="bearish",
        confidence=0.5,
        evidence=[Evidence(id=f"S{i}", fact=f"Sentiment fact {i}") for i in range(1, 4)],
    )


def make_board_state(**overrides: object) -> RequestState:
    """A `RequestState` that has passed the signals board and is routed to
    `debate`: fixed signals (evidence T1-T6, F1-F5, S1-S3), account
    $100,000 / $96,000, reference $182, ATR $4. Override any field, e.g.
    `make_board_state(debate=[...])`."""
    signals = {
        "technical": _technical_signal(),
        "fundamentals": _fundamentals_signal(),
        "sentiment": _sentiment_signal(),
    }
    board = build_board(signals, conflict_min_confidence=0.4)

    state = RequestState(
        request_id="20241018-AAPL-test",
        mode="backtest",
        as_of=AS_OF,
        ticker="AAPL",
        company_name="Apple Inc.",
        account=Account(cash=Decimal("96000"), equity=Decimal("100000")),
        position=None,
        prices=PriceSnapshot(
            source="yfinance",
            bars=[Bar(date=AS_OF, open=180.0, high=183.0, low=179.0, close=182.0, volume=1e7)],
            splits=[],
            reference_price=REFERENCE_PRICE,
        ),
        indicators=Indicators(
            close=182.0,
            sma_20=175.0,
            sma_50=170.0,
            above_sma_20=True,
            above_sma_50=True,
            rsi_14=60.0,
            atr_14=ATR,
            volatility=0.25,
            return_1w=0.02,
            return_1m=0.05,
            return_3m=0.10,
        ),
        technical_signal=signals["technical"],
        fundamentals_signal=signals["fundamentals"],
        sentiment_signal=signals["sentiment"],
        board=board,
        route="debate",
    )
    return state.model_copy(update=overrides)


@pytest.fixture
def board_state() -> RequestState:
    return make_board_state()


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """Overrides the base `settings` fixture (tests/conftest.py): a node
    test scripts several large-role calls in one test, so the per-minute
    limits are raised here so the gateway's real pacing never sleeps
    through them (plan sec13, the same override the graph tests use)."""
    return settings.model_copy(update={"llm_tpm_limit": 1_000_000, "llm_rpm_limit": 1_000})


def make_reply(
    content: str, *, input_tokens: int = 50, output_tokens: int = 10, reasoning_tokens: int = 5
) -> CompletionReply:
    return CompletionReply(
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    )


class ScriptedLLM:
    """Records every rendered prompt; answers with queued replies, matched
    by which fixed first line the prompt starts with, consumed in order (so
    a test can script a call and its retry as two queued entries for the
    same template).
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self._queues: dict[str, deque[CompletionReply]] = defaultdict(deque)
        self._lock = threading.Lock()

    def queue(self, first_line: str, reply: CompletionReply) -> None:
        self._queues[first_line].append(reply)

    def __call__(self, request: CompletionRequest) -> CompletionReply:
        prompt = request.messages[0]["content"]
        with self._lock:
            self.prompts.append(prompt)
            for first_line, queue in self._queues.items():
                if prompt.startswith(first_line) and queue:
                    return queue.popleft()
            raise AssertionError(f"no scripted reply queued for: {prompt[:80]!r}")
