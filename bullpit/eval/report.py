"""The results page: reads finished backtest runs from the journal, scores each
with `eval/metrics.py`, and writes `results.md` plus three PNG charts
(architecture §12; M7 specs-plan FR-11, FR-12, §11; D-M7-14, D-M7-16).

This is the evaluation's only I/O edge. No LLM is called: every number and
every comparison sentence comes from code.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import matplotlib
import pandas as pd
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.data.calendar import decision_days
from bullpit.data.prices import get_prices
from bullpit.domain import Account, Bar, Trade
from bullpit.errors import ConfigError
from bullpit.eval import metrics
from bullpit.eval.baselines import Policy
from bullpit.journal.models import (
    BacktestRun,
    EquitySnapshot,
    LLMCall,
    RecommendationRecord,
    Request,
    TradeRecord,
)
from bullpit.risk.rules import stage_a
from bullpit.runners.backtest import trade_from_row
from bullpit.tools.indicators import compute_indicators

matplotlib.use("Agg")  # static PNGs, no display (D-M7-15)
import matplotlib.pyplot as plt

_AI_POLICIES: frozenset[Policy] = frozenset({"bullpit", "single_agent"})


class RunScore(BaseModel):
    """One run's metrics, ready for the table and the charts."""

    run_id: str
    policy: str
    curve: list[tuple[date, Decimal]]  # daily equity, oldest first
    total_return: float
    sharpe: float | None
    max_drawdown: float
    win_rate: float | None
    profit_factor: float | None
    buy_decisions: int
    entered: int
    closed: int
    open_at_end: int
    open_at_end_pnl: Decimal
    no_trade: metrics.NoTradeValue
    not_sizeable: int
    brier: float | None
    bins: list[metrics.CalibrationBin]
    tokens: metrics.TokenCost


def _load_runs(run_ids: Sequence[str], sessions: sessionmaker[Session]) -> list[BacktestRun]:
    """Every run must be completed and share tickers and start date, so the
    table compares like with like (M7-FR-11)."""
    with sessions() as session:
        runs = [session.get(BacktestRun, run_id) for run_id in run_ids]
    found: list[BacktestRun] = []
    for run_id, run in zip(run_ids, runs, strict=True):
        if run is None:
            raise ConfigError(f"No backtest run {run_id!r}.")
        if run.status != "completed":
            raise ConfigError(f"Run {run_id} is {run.status}, not completed.")
        found.append(run)
    first = found[0]
    for run in found[1:]:
        if (run.tickers, run.start_date) != (first.tickers, first.start_date):
            raise ConfigError(f"Run {run.id} has other tickers or start date than run {first.id}.")
    return found


def _bars(frame: pd.DataFrame) -> list[Bar]:
    return [
        Bar(
            date=cast(pd.Timestamp, index).date(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for index, row in frame.iterrows()
    ]


def _no_trade_trades(
    equity_on: dict[date, Decimal],
    no_trade_days: list[tuple[date, str]],
    history: dict[str, pd.DataFrame],
    settings: Settings,
) -> tuple[list[Trade], int]:
    """The hypothetical trade of every "no trade" request before the last
    decision day (§11.2): fixed defaults, an empty account with that day's
    equity. Returns the trades and how many couldn't be sized."""
    style = settings.baseline_exit_style
    stop_atr: Decimal = getattr(settings, f"exit_stop_atr_{style}")
    trades: list[Trade] = []
    not_sizeable = 0
    for day, ticker in no_trade_days:
        frame = history[ticker]
        stamp = pd.Timestamp(day)
        atr = compute_indicators(frame[frame.index <= stamp]).atr_14
        equity = equity_on[day]
        order = stage_a(
            ticker=ticker,
            reference=Decimal(str(frame.loc[stamp, "close"])),
            atr=None if atr is None else Decimal(str(atr)),
            exit_style=style,
            target_weight=settings.baseline_target_weight,
            account=Account(cash=equity, equity=equity),
            held_value=Decimal(0),
            stop_atr=stop_atr,
            reward_risk=settings.exit_reward_risk,
            risk_pct=settings.risk_per_trade_pct,
            cap_pct=settings.max_position_pct,
        )
        if isinstance(order, str):
            not_sizeable += 1
            continue
        trades.append(
            metrics.hypothetical_trade(
                order,
                submitted_on=day,
                bars=_bars(frame[frame.index > stamp]),
                cash=equity,
                slippage_pct=settings.sim_slippage_pct,
            )
        )
    return trades, not_sizeable


def _score_run(
    run: BacktestRun,
    history: dict[str, pd.DataFrame],
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
) -> RunScore:
    start = Decimal(run.starting_cash)
    with sessions() as session:
        curve = [
            (row.day, Decimal(row.equity))
            for row in session.scalars(
                select(EquitySnapshot)
                .where(EquitySnapshot.run_id == run.id)
                .order_by(EquitySnapshot.day)
            )
        ]
        requests = list(session.scalars(select(Request).where(Request.run_id == run.id)))
        trade_rows = list(session.scalars(select(TradeRecord).where(TradeRecord.run_id == run.id)))
        request_ids = [request.id for request in requests]
        # A resumed run replays the calls it already made from the cache; each
        # distinct call counts once, as the real call when there is one.
        distinct: dict[tuple[str, str], LLMCall] = {}
        for call in session.scalars(select(LLMCall).where(LLMCall.request_id.in_(request_ids))):
            key = (call.request_id, call.cache_key)
            if key not in distinct or distinct[key].cache_hit:
                distinct[key] = call
        calls = list(distinct.values())
        hit_keys = {call.cache_key for call in calls if call.cache_hit}
        original = {
            call.cache_key: call.input_tokens + call.output_tokens + call.reasoning_tokens
            for call in session.scalars(
                select(LLMCall).where(LLMCall.cache_key.in_(hit_keys), LLMCall.cache_hit.is_(False))
            )
        }
        confidence: dict[str, float] = {}
        for attempt in session.scalars(
            select(RecommendationRecord)
            .where(RecommendationRecord.request_id.in_(request_ids))
            .order_by(RecommendationRecord.attempt)
        ):
            confidence[attempt.request_id] = attempt.confidence

    equity_on = dict(curve)
    decision_equity = [equity_on[day] for day in decision_days(run.start_date, run.weeks)]
    weekly = metrics.weekly_returns(start, decision_equity)
    trades = [(row.request_id, trade_from_row(row)) for row in trade_rows]
    closed = [(request_id, trade) for request_id, trade in trades if trade.status == "closed"]
    marked = [trade for _, trade in trades if trade.status == "open_at_end"]
    pnls = [trade.pnl for _, trade in closed if trade.pnl is not None]

    hypothetical, not_sizeable = _no_trade_trades(
        equity_on,
        [
            (request.as_of, request.ticker)
            for request in requests
            if request.outcome == "no_trade" and request.as_of < run.end_date
        ],
        history,
        settings,
    )
    pairs = (
        [(confidence[request_id], (trade.pnl or Decimal(0)) > 0) for request_id, trade in closed]
        if cast(Policy, run.policy) in _AI_POLICIES
        else []
    )
    return RunScore(
        run_id=run.id,
        policy=run.policy,
        curve=curve,
        total_return=metrics.total_return(start, curve[-1][1]),
        sharpe=metrics.sharpe(weekly),
        max_drawdown=metrics.max_drawdown([start, *(value for _, value in curve)]),
        win_rate=metrics.win_rate(pnls),
        profit_factor=metrics.profit_factor(pnls),
        buy_decisions=sum(1 for request in requests if request.outcome == "buy"),
        entered=sum(1 for _, trade in trades if trade.entry_price is not None),
        closed=len(closed),
        open_at_end=len(marked),
        open_at_end_pnl=sum((trade.pnl or Decimal(0) for trade in marked), Decimal(0)),
        no_trade=metrics.no_trade_value(hypothetical),
        not_sizeable=not_sizeable,
        brier=metrics.brier(pairs),
        bins=metrics.calibration(pairs, settings.eval_calibration_bins),
        tokens=metrics.tokens_per_request(
            [
                metrics.CallRow(
                    cache_key=call.cache_key,
                    cache_hit=call.cache_hit,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    reasoning_tokens=call.reasoning_tokens,
                )
                for call in calls
            ],
            original,
            len(requests),
        ),
    )


def _pct(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.2f}%" if signed else f"{value * 100:.2f}%"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _comparison(name: str, value: float, other_name: str, other: float) -> str:
    relation = "above" if value > other else "below" if value < other else "equal to"
    return (
        f"- {name} ({_pct(value, signed=True)}) is {relation} "
        f"{other_name} ({_pct(other, signed=True)})."
    )


def _table(scores: Sequence[RunScore], held: dict[str, float]) -> list[str]:
    columns = [
        "Approach",
        "Run",
        "Total return",
        "Sharpe",
        "Max drawdown",
        "Win rate",
        "Profit factor",
        "Buy decisions",
        "Trades entered (closed / open at end)",
        "Open-at-end P&L",
        '"No trade" value',
        "Brier",
        "Tokens per request",
    ]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for score in scores:
        skipped = score.no_trade
        cells = [
            score.policy,
            score.run_id,
            _pct(score.total_return, signed=True),
            _number(score.sharpe),
            _pct(score.max_drawdown),
            _pct(score.win_rate),
            _number(score.profit_factor),
            str(score.buy_decisions),
            f"{score.entered} ({score.closed} / {score.open_at_end})",
            f"{score.open_at_end_pnl:,.2f}",
            f"{skipped.count} trades, P&L {skipped.pnl:,.2f} ({score.not_sizeable} not sizeable)",
            _number(score.brier),
            f"{score.tokens.per_request:,.0f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    for ticker, value in held.items():
        cells = [f"buy and hold {ticker}", "n/a", _pct(value, signed=True)] + ["n/a"] * (
            len(columns) - 3
        )
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _plot_curves(scores: Sequence[RunScore], path: Path, *, drawdown: bool) -> None:
    figure, axes = plt.subplots(figsize=(8, 4))
    for score in scores:
        days = pd.DatetimeIndex([pd.Timestamp(day) for day, _ in score.curve])
        values = [float(value) for _, value in score.curve]
        if drawdown:
            peaks = itertools.accumulate(values, max)
            values = [(v - peak) / peak * 100 for v, peak in zip(values, peaks, strict=True)]
        axes.plot(days, values, label=f"{score.policy} ({score.run_id})")
    axes.set_title("Drawdown" if drawdown else "Equity")
    axes.set_ylabel("% below peak" if drawdown else "Equity ($)")
    axes.legend()
    figure.autofmt_xdate()
    figure.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(figure)


def _plot_calibration(scores: Sequence[RunScore], path: Path) -> None:
    figure, axes = plt.subplots(figsize=(5, 5))
    axes.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfectly calibrated")
    for score in scores:
        if score.bins:
            axes.plot(
                [b.mean_confidence for b in score.bins],
                [b.win_share for b in score.bins],
                marker="o",
                label=f"{score.policy} ({score.run_id})",
            )
    axes.set_title("Calibration: confidence vs share of closed buys that won")
    axes.set_xlabel("Mean confidence")
    axes.set_ylabel("Win share")
    axes.legend()
    figure.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(figure)


def _page(runs: Sequence[BacktestRun], scores: Sequence[RunScore], held: dict[str, float]) -> str:
    """The Markdown. The comparison sentences and the limits are fixed text
    filled from the data; nothing else is concluded (M7-FR-12)."""
    first = runs[0]
    pinned_models = {
        "small": Settings.model_fields["llm_small_model"].default,
        "large": Settings.model_fields["llm_large_model"].default,
    }
    ai_models = [run.models for run in runs if run.policy in _AI_POLICIES]
    pinned = all(models == pinned_models for models in ai_models)
    trades = sum(score.entered for score in scores)
    lines = [
        "# Results",
        "",
        "## Setup",
        "",
        f"- Stocks: {', '.join(first.tickers)}",
        f"- Window: {first.start_date} to {first.end_date} ({first.weeks} weeks, "
        "one decision on each week's last session)",
        f"- Starting cash: ${Decimal(first.starting_cash):,.0f}; the same broker, sizing "
        "limits, exits and slippage for every approach",
        "- Runs: "
        + "; ".join(f"{run.policy} {run.id} (commit {run.git_commit[:7]})" for run in runs),
        "- Models of the AI approaches: "
        + ("; ".join(sorted({str(models) for models in ai_models})) or "none")
        + (" (the pinned Groq models)" if pinned else " (a free OpenRouter model, not pinned)"),
        "",
        "## Results",
        "",
        *_table(scores, held),
        "",
        "![Equity](equity.png)",
        "",
        "![Drawdown](drawdown.png)",
        "",
        "![Calibration](calibration.png)",
        "",
        "## Comparison (total return only)",
        "",
    ]
    for one, other in itertools.combinations(scores, 2):
        lines.append(
            _comparison(
                f"{one.policy} {one.run_id}",
                one.total_return,
                f"{other.policy} {other.run_id}",
                other.total_return,
            )
        )
    for score, (ticker, value) in itertools.product(scores, held.items()):
        lines.append(
            _comparison(
                f"{score.policy} {score.run_id}",
                score.total_return,
                f"{ticker} buy and hold",
                value,
            )
        )
    lines += [
        "",
        f"A {first.weeks}-week, {len(first.tickers)}-stock pilot can't tell skill from luck.",
        "",
        "## Limits",
        "",
        f"- **Sample size.** {trades} trades entered across all approaches, over "
        f"{first.weeks} weeks and {len(first.tickers)} stocks: far too little to separate "
        f"skill from luck. Sharpe comes from only {first.weeks} weekly returns, so treat it "
        "as a formality.",
        "- **One seed.** Each approach ran once. Repeat seeds need a provider that accepts a "
        "seed, and the free Qwen route does not. Repeats, the full-length run and the "
        "debate-impact measure are carried over.",
        "- **Model.** "
        + (
            "The AI approaches used the pinned Groq models."
            if pinned
            else "The AI approaches used a free OpenRouter model, not the pinned gpt-oss "
            "models, so this says little about Bull Pit on the pinned pair."
        ),
        "- **Fills are approximate.** Simulated fills use the next open plus slippage and "
        "daily bars (ADR-0005).",
        "- **Stocks.** They were chosen by a rule that favours large, surviving companies "
        "(ADR-0006).",
        "- **Buy and hold** is fully invested; the approaches are mostly in cash, so their "
        "returns are not directly comparable.",
        "",
    ]
    if not pinned:
        lines += [
            "## Why a pilot on a free model, and what comes next",
            "",
            "Bull Pit is built to cost nothing to run, so this pilot uses the free "
            "`qwen/qwen3.8-27b:free` route on OpenRouter instead of a paid model. That route "
            "has limits that shaped the result: a small shared daily quota (about 50 requests), "
            'frequent "rate-limited upstream" pauses that made runs slow, no `seed` setting so '
            "runs can't be repeated exactly, no JSON mode, and it is not the pinned gpt-oss "
            "pair the system was designed around.",
            "",
            "A complete test (26 weeks, several stocks, repeat seeds) needs about 300 "
            "requests or more, which the free tiers can't cover. Running it needs a model "
            "with paid credit, which goes against the free-of-cost rule, so it is left for "
            "later. The commands are in the M7 retrospective, and the same `bullpit eval` "
            "will then produce the full comparison.",
            "",
            "What this pilot does show is that the pipeline works end to end: all five "
            "approaches ran on the same broker, stocks and dates, every metric was computed "
            "from the journal, and this page and its charts were produced by code. "
            "It does not show that any approach is better than another.",
            "",
        ]
    return "\n".join(lines)


def evaluate(
    run_ids: Sequence[str], out_dir: Path, *, settings: Settings, sessions: sessionmaker[Session]
) -> Path:
    """Scores the runs and writes `results.md`, `equity.png`, `drawdown.png` and
    `calibration.png` into `out_dir`. Returns the path of `results.md`.

    Raises `ConfigError` if a run isn't completed or the runs don't share
    tickers and start date, and `DataUnavailable` if prices are missing; in
    both cases nothing is written.
    """
    runs = _load_runs(run_ids, sessions)
    first = runs[0]
    history = {
        ticker: get_prices(
            ticker, first.end_date, settings.price_history_sessions, settings=settings
        ).bars
        for ticker in first.tickers
    }
    scores = [_score_run(run, history, settings=settings, sessions=sessions) for run in runs]
    held: dict[str, float] = {}
    for ticker, frame in history.items():
        window = frame[frame.index >= pd.Timestamp(first.start_date)]
        held[ticker] = metrics.buy_and_hold(
            Decimal(str(window["open"].iloc[0])),
            Decimal(str(window["close"].iloc[-1])),
            settings.sim_slippage_pct,
        )
    text = _page(runs, scores, held)

    out_dir.mkdir(parents=True, exist_ok=True)
    _plot_curves(scores, out_dir / "equity.png", drawdown=False)
    _plot_curves(scores, out_dir / "drawdown.png", drawdown=True)
    _plot_calibration(scores, out_dir / "calibration.png")
    path = out_dir / "results.md"
    path.write_text(text, encoding="utf-8")
    return path
