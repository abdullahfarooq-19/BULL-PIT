"""Response bodies of the API (M8 specs-plan sec5, FR-18, FR-19). They reuse
`Report`, `Trade`, `ApprovalDecision` and `ApprovalProblem` rather than copy them.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from bullpit.approval.gate import ApprovalDecision
from bullpit.domain import OrderType, Trade


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
    overrides: list[str] = Field(
        default_factory=list
    )  # the approval's overrides, for the badge (M11.1-FR-19)


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
    order_type: str | None  # of an approved order (M11.1)
    overrides: list[str]  # of the approval; non-empty gets the "override" badge


class RequestDetail(RequestSummary):
    stage: str  # starting | checking | analysts | debate | trader | risk | report | ...
    debate_round: int | None
    approval: ApprovalDecision | None
    trade: TradeOut | None


HistoryState = Literal[
    "analysing",
    "decision_pending",
    "rejected_by_you",
    "order_placed",
    "waiting_at_limit",
    "open",
    "closed",
    "cancelled",
    "expired",
    "no_decision",
    "no_trade",
    "rejected_by_check",
    "failed",
]


class HistoryRow(BaseModel, frozen=True):
    """One live request on the Trades History page (M11.2-FR-9 to FR-12). The
    numbers come from the trade, else the approval, else the report's plan."""

    id: str
    ticker: str
    created_at: datetime
    as_of: date
    state: HistoryState
    outcome: str | None  # buy | no_trade
    status_reason: str | None
    expires_at: datetime | None  # only while the report waits for a decision
    order_type: str | None
    overrides: list[str]
    shares: int | None
    plan_price: Decimal | None  # the report's reference price
    entry_price: Decimal | None  # the fill
    limit_price: Decimal | None
    take_profit: Decimal | None
    stop_loss: Decimal | None
    exit_price: Decimal | None
    exit_date: date | None
    exit_reason: str | None
    cancel_reason: str | None
    pnl: Decimal | None
    current_price: Decimal | None  # open trades only (M11.3-FR-1)
    unrealised_pnl: Decimal | None


class AccountOut(BaseModel, frozen=True):
    """The broker account card (M11.2-FR-1, FR-2)."""

    broker: str
    account_type: Literal["demo"]  # the paper-only guard makes "live" impossible
    account_number: str  # masked
    status: str
    equity: Decimal
    cash: Decimal
    last_equity: Decimal
    day_change: Decimal
    day_change_pct: Decimal | None  # None when last_equity is 0


class MarketOut(BaseModel, frozen=True):
    """Whether the US market is open and when it next changes (M11.3-FR-12)."""

    is_open: bool
    next_open: datetime
    next_close: datetime


class PortfolioStats(BaseModel, frozen=True):
    """Realised statistics of the live journal (M11.2-FR-18)."""

    approved: int
    rejected: int
    ongoing: int
    closed: int
    total_profit: Decimal
    total_loss: Decimal  # zero or negative
    net_pnl: Decimal


class WatchlistStock(BaseModel, frozen=True):
    symbol: str
    name: str
    liked: bool
    liked_at: datetime | None


class OrderPreviewBody(BaseModel, frozen=True):
    """What the order box asks the preview to price (M11.1-FR-10)."""

    order_type: OrderType = "market"
    limit_price: Decimal | None = None
    advanced: bool = False
    shares: int | None = None  # None: the recommended count
    stop_loss: Decimal | None = None  # advanced only
    take_profit: Decimal | None = None  # advanced only

    @model_validator(mode="after")
    def _limit_needs_a_price(self) -> OrderPreviewBody:
        if self.order_type == "limit" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("limit_price is required for a limit order")
        return self


class PreviewWarning(BaseModel, frozen=True):
    code: str
    message: str


class OrderPreview(BaseModel, frozen=True):
    """The order the chosen mode would place, priced from the live price, with
    nothing placed (M11.1-FR-10). Every number is `None` when it can't be priced
    (no price for a market order, or exits that can't hold); `warnings` say why."""

    price: Decimal | None  # Alpaca's latest trade; None when it couldn't be read
    fetched_at: datetime
    order_type: OrderType
    entry_price: Decimal | None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    shares: int
    max_shares: int | None = None
    cost: Decimal | None = None
    max_loss: Decimal | None = None
    max_gain: Decimal | None = None
    pct_of_equity: Decimal | None = None
    loss_pct_of_equity: Decimal | None = None
    position_pct_after: Decimal | None = None
    overrides: list[str]
    warnings: list[PreviewWarning]


class ApprovalResult(BaseModel, frozen=True):
    approval: ApprovalDecision
    trade: TradeOut | None


class EquityPoint(BaseModel, frozen=True):
    date: date
    equity: Decimal
