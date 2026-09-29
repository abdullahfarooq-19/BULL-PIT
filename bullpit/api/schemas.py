"""Response bodies of the API (M8 specs-plan sec5, FR-18, FR-19). They reuse
`Report`, `Trade`, `ApprovalDecision` and `ApprovalProblem` rather than copy them.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from bullpit.approval.gate import ApprovalDecision
from bullpit.domain import Trade


class Problem(BaseModel, frozen=True):
    """A refusal: a stable `code` and a message. No stack trace, key or config
    snapshot ever appears in one (M8-FR-19). Approval refusals send the richer
    `ApprovalProblem` (both prices, the largest share count that fits)."""

    code: str
    message: str


class NewRequest(BaseModel, frozen=True):
    ticker: str


class RequestStarted(BaseModel, frozen=True):
    request_id: str


class TradeOut(Trade):
    """A live or simulated trade with the request it belongs to."""

    request_id: str


class RequestSummary(BaseModel, frozen=True):
    id: str
    ticker: str
    as_of: date
    status: str
    status_reason: str | None
    outcome: str | None  # buy | no_trade
    created_at: datetime
    expires_at: datetime | None  # only while the report waits for a decision
    decision: str | None  # approved | rejected


class RequestDetail(RequestSummary):
    stage: str  # starting | checking | analysts | debate | trader | risk | report | ...
    debate_round: int | None
    approval: ApprovalDecision | None
    trade: TradeOut | None


class ApprovalResult(BaseModel, frozen=True):
    approval: ApprovalDecision
    trade: TradeOut | None


class EquityPoint(BaseModel, frozen=True):
    date: date
    equity: Decimal


class BacktestRunOut(BaseModel, frozen=True):
    id: str
    policy: str
    tickers: list[str]
    start_date: date
    end_date: date
    weeks: int
    status: str
    status_reason: str | None
    created_at: datetime
    last_equity: Decimal | None


class BacktestDetail(BacktestRunOut):
    seed: int
    starting_cash: Decimal
    models: dict[str, str]
    trades: list[TradeOut]
    equity: list[EquityPoint]


class ResultsPage(BaseModel, frozen=True):
    markdown: str
    images: list[str]
