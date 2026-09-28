"""The paper-only safety guard.

Bull Pit must never place a real order (architecture Part 14; CLAUDE.md).
`assert_paper_url` is the one function that decides whether a base URL is
allowed, and it's pure: no I/O, no settings, no way to configure it off.
`bullpit/broker/clients.py` is the only place that's allowed to build a
trading client, and it always calls this first.
"""

from __future__ import annotations

from typing import Final
from urllib.parse import SplitResult, urlsplit

from bullpit.errors import LiveTradingRefused

PAPER_TRADING_HOST: Final = "paper-api.alpaca.markets"
PAPER_TRADING_URL: Final = f"https://{PAPER_TRADING_HOST}"


def assert_paper_url(url: str) -> str:
    """Return the normalised paper-trading URL, or raise ``LiveTradingRefused``.

    Every part of the URL is checked explicitly (scheme, host, port, path,
    user info, query, fragment) by comparing parsed components, never by
    substring matching, so a URL like ``https://paper-api.alpaca.markets.evil.com``
    or ``https://evil.com/?h=paper-api.alpaca.markets`` is refused too.
    """
    if not url:
        raise LiveTradingRefused(
            "ALPACA_BASE_URL is empty. It must be exactly "
            f"'{PAPER_TRADING_URL}'. Bull Pit only ever trades on Alpaca's "
            "paper endpoint; there is no setting to change this."
        )

    parts: SplitResult = urlsplit(url)

    ok = (
        parts.scheme == "https"
        and (parts.hostname or "").lower() == PAPER_TRADING_HOST
        and parts.port is None
        and not parts.username
        and not parts.password
        and parts.path in ("", "/")
        and not parts.query
        and not parts.fragment
    )
    if not ok:
        raise LiveTradingRefused(
            f"Refusing to trade against '{url}'. The Alpaca base URL must be "
            f"exactly '{PAPER_TRADING_URL}' (paper trading only, no real money, "
            "ever). There is no setting to change this."
        )
    return PAPER_TRADING_URL
