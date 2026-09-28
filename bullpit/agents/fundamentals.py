"""Fundamentals analyst: code computes the ratios and writes the evidence
facts; the LLM judges only the filing-derived numbers, never P/E, which
moves with the daily price (architecture Part 6; M3-FR-10, FR-11, FR-12;
D10, D-M3-1).
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.data.sec import get_sec_facts
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import AnalystVerdict, Evidence, Signal
from bullpit.state import RequestState
from bullpit.tools.fundamentals import FundamentalsMetrics, compute_fundamentals

_TEMPLATE = "fundamentals.md"
_SAFE_DEFAULT = AnalystVerdict(direction="neutral", confidence=0.0)
_PE_EVIDENCE_ID = "F4"  # excluded from the prompt: evidence-only (D10, FR-11)


def _dollars(value: float) -> str:
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    return f"${value / 1e6:.2f}M"


def _revenue_fact(metrics: FundamentalsMetrics, latest_revenue: float) -> str:
    base = (
        f"Revenue for the quarter ended {metrics.latest_quarter_end} was {_dollars(latest_revenue)}"
    )
    if metrics.revenue_growth_yoy is None:
        return f"{base}; no comparable quarter a year earlier"
    return f"{base}, {metrics.revenue_growth_yoy * 100:+.1f}% on a year earlier"


def _margin_fact(metrics: FundamentalsMetrics) -> str:
    if metrics.net_margin is None:
        return "Net margin for that quarter is not available"
    return f"Net margin for that quarter was {metrics.net_margin * 100:.1f}%"


def _eps_fact(metrics: FundamentalsMetrics) -> str:
    if metrics.ttm_eps is None:
        return "Diluted EPS over the last 4 quarters is not available"
    return f"Diluted EPS over the last 4 quarters was {metrics.ttm_eps:.2f}"


def _pe_fact(metrics: FundamentalsMetrics) -> str:
    if metrics.pe is not None:
        return f"P/E is {metrics.pe:.1f} at the reference price"
    if metrics.ttm_eps is not None and metrics.ttm_eps <= 0:
        return "P/E is not meaningful: negative earnings"
    return "P/E is not available"


def _filing_fact(metrics: FundamentalsMetrics) -> str:
    return (
        f"Latest filing: {metrics.filing_form} for the period ended "
        f"{metrics.filing_period_end}, filed {metrics.filing_date}"
    )


def evidence_from_metrics(metrics: FundamentalsMetrics, *, latest_revenue: float) -> list[Evidence]:
    return [
        Evidence(id="F1", fact=_revenue_fact(metrics, latest_revenue)),
        Evidence(id="F2", fact=_margin_fact(metrics)),
        Evidence(id="F3", fact=_eps_fact(metrics)),
        Evidence(id=_PE_EVIDENCE_ID, fact=_pe_fact(metrics)),
        Evidence(id="F5", fact=_filing_fact(metrics)),
    ]


def fundamentals_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    if state.prices is None:
        raise ValueError("fundamentals_node runs after request_check populates prices")

    facts = get_sec_facts(state.ticker, state.as_of, settings=settings)
    metrics = compute_fundamentals(
        facts.facts,
        reference_price=float(state.prices.reference_price),
        splits=state.prices.splits,
    )

    if metrics.latest_revenue is None or metrics.latest_net_income is None:
        signal = Signal(
            ticker=state.ticker,
            analyst="fundamentals",
            direction="neutral",
            confidence=0.0,
            evidence=[],
            flagged=True,
            note="revenue or net income not available for the latest quarter",
        )
        return {"fundamentals": metrics, "fundamentals_signal": signal}

    full_evidence = evidence_from_metrics(metrics, latest_revenue=metrics.latest_revenue)
    prompt_evidence = [item for item in full_evidence if item.id != _PE_EVIDENCE_ID]

    result = call_llm(
        Role.SMALL,
        _TEMPLATE,
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "evidence": [item.model_dump() for item in prompt_evidence],
        },
        AnalystVerdict,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    if result.flagged:
        signal = Signal(
            ticker=state.ticker,
            analyst="fundamentals",
            direction="neutral",
            confidence=0.0,
            evidence=full_evidence,
            flagged=True,
            note="LLM reply invalid after retry",
        )
    else:
        signal = Signal(
            ticker=state.ticker,
            analyst="fundamentals",
            direction=result.value.direction,
            confidence=result.value.confidence,
            evidence=full_evidence,
        )

    return {"fundamentals": metrics, "fundamentals_signal": signal}
