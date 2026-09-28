"""`bullpit doctor`: checks settings and every external service, by hand.

Each check is independent, catches every exception, and never lets a secret,
a full response body, or a stack trace reach the output (dev-plan.md M0-FR-16).
A check whose dependency failed is skipped rather than attempted, so a
missing key produces one clear failure instead of a wall of network errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import httpx

from bullpit.broker.clients import make_data_clients, make_trading_client
from bullpit.config import Settings
from bullpit.data.sec import sec_user_agent

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"  # Apple


class Status(StrEnum):
    OK = "OK"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str = ""

    def line(self) -> str:
        detail = f"    {self.detail}" if self.detail else ""
        return f"{self.name:<15} {self.status.value:<5}{detail}"


def check_config(settings: Settings) -> CheckResult:
    missing = settings.missing_secrets()
    if missing:
        return CheckResult("config", Status.FAIL, f"missing: {', '.join(missing)}")
    return CheckResult("config", Status.OK)


def check_paper_guard(settings: Settings) -> CheckResult:
    # Settings() already ran the guard at load time; reaching here means it
    # passed. This check makes that fact visible in the report.
    return CheckResult("paper-guard", Status.OK, settings.alpaca_base_url)


def check_alpaca_trading(settings: Settings) -> CheckResult:
    try:
        client = make_trading_client(settings)
        account = client.get_account()
    except Exception as exc:
        return CheckResult("alpaca-trading", Status.FAIL, f"{type(exc).__name__}: {exc}")
    status = getattr(account, "status", None)
    cash = getattr(account, "cash", "?")
    equity = getattr(account, "equity", "?")
    return CheckResult(
        "alpaca-trading", Status.OK, f"status {status}, cash {cash}, equity {equity}"
    )


def check_alpaca_data(settings: Settings) -> CheckResult:
    try:
        from alpaca.data.requests import NewsRequest

        clients = make_data_clients(settings)
        news = clients.news.get_news(NewsRequest(symbols="AAPL", limit=1))
    except Exception as exc:
        return CheckResult("alpaca-data", Status.FAIL, f"{type(exc).__name__}: {exc}")
    articles = getattr(news, "data", None) or getattr(news, "news", None)
    if not articles:
        return CheckResult("alpaca-data", Status.FAIL, "no news articles returned")
    return CheckResult("alpaca-data", Status.OK, "news reachable")


def check_groq(settings: Settings, *, timeout: float) -> CheckResult:
    if settings.groq_api_key is None:
        return CheckResult("groq", Status.FAIL, "GROQ_API_KEY is not set")
    try:
        response = httpx.get(
            GROQ_MODELS_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key.get_secret_value()}"},
            timeout=timeout,
        )
        response.raise_for_status()
        model_ids = {m["id"] for m in response.json().get("data", [])}
    except Exception as exc:
        return CheckResult("groq", Status.FAIL, f"{type(exc).__name__}: {exc}")
    wanted = {settings.llm_small_model, settings.llm_large_model}
    missing = wanted - model_ids
    if missing:
        return CheckResult("groq", Status.FAIL, f"model(s) not served: {', '.join(missing)}")
    return CheckResult("groq", Status.OK, f"{', '.join(sorted(wanted))} served")


def check_sec(settings: Settings, *, timeout: float) -> CheckResult:
    try:
        response = httpx.get(
            SEC_SUBMISSIONS_URL,
            headers={"User-Agent": sec_user_agent(settings)},
            timeout=timeout,
        )
        response.raise_for_status()
    except Exception as exc:
        return CheckResult("sec", Status.FAIL, f"{type(exc).__name__}: {exc}")
    return CheckResult("sec", Status.OK, "data.sec.gov reachable")


def check_yfinance(*, timeout: float) -> CheckResult:
    try:
        import yfinance as yf

        bars = yf.Ticker("SPY").history(period="5d", timeout=timeout)
    except Exception as exc:
        return CheckResult("yfinance", Status.FAIL, f"{type(exc).__name__}: {exc}")
    if bars is None or bars.empty:
        return CheckResult("yfinance", Status.FAIL, "no bars returned for SPY")
    return CheckResult("yfinance", Status.OK, "SPY bars reachable")


def run_all_checks(settings: Settings) -> list[CheckResult]:
    """Run every check in order, skipping ones whose dependency already failed."""
    results: list[CheckResult] = []

    config_result = check_config(settings)
    results.append(config_result)
    config_ok = config_result.status is Status.OK

    if config_ok:
        results.append(check_paper_guard(settings))
    else:
        results.append(CheckResult("paper-guard", Status.SKIP, "config failed"))
    paper_guard_ok = results[-1].status is Status.OK

    if config_ok and paper_guard_ok:
        results.append(check_alpaca_trading(settings))
    else:
        results.append(CheckResult("alpaca-trading", Status.SKIP, "config or paper-guard failed"))

    if config_ok:
        results.append(check_alpaca_data(settings))
        results.append(check_groq(settings, timeout=settings.http_timeout_seconds))
        results.append(check_sec(settings, timeout=settings.http_timeout_seconds))
    else:
        results.append(CheckResult("alpaca-data", Status.SKIP, "config failed"))
        results.append(CheckResult("groq", Status.SKIP, "config failed"))
        results.append(CheckResult("sec", Status.SKIP, "config failed"))

    results.append(check_yfinance(timeout=settings.http_timeout_seconds))

    return results
