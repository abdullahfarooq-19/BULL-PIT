"""The paper-only guard must refuse every non-paper Alpaca URL, always.

This is the one automated test M0 requires (dev-plan.md sec7.1: "Safety
refusals"). It proves LiveTradingRefused is raised *before* any network call
by patching the SDK's TradingClient constructor and asserting it's never
invoked for a bad URL. pytest-socket backs this up at the transport level.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bullpit.broker.clients import make_trading_client
from bullpit.broker.safety import PAPER_TRADING_URL, assert_paper_url
from bullpit.config import Settings
from bullpit.errors import LiveTradingRefused

REJECTED_URLS = [
    pytest.param("https://api.alpaca.markets", id="live-host"),
    pytest.param("http://paper-api.alpaca.markets", id="http-not-https"),
    pytest.param("https://paper-api.alpaca.markets:8443", id="explicit-port"),
    pytest.param("https://paper-api.alpaca.markets/v2", id="path-suffix"),
    pytest.param("https://paper-api.alpaca.markets.evil.com", id="host-suffix-attack"),
    pytest.param("https://user@paper-api.alpaca.markets", id="userinfo"),
    pytest.param("https://evil.com/?h=paper-api.alpaca.markets", id="query-string-attack"),
    pytest.param("", id="empty-string"),
]


def _settings(base_url: str) -> Settings:
    """A Settings object with explicit values, never reading a real .env."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        alpaca_base_url=base_url,
        alpaca_api_key="fake-key",
        alpaca_secret_key="fake-secret",
    )


class TestAssertPaperUrl:
    @pytest.mark.parametrize("url", REJECTED_URLS)
    def test_rejects_non_paper_urls(self, url: str) -> None:
        with pytest.raises(LiveTradingRefused):
            assert_paper_url(url)

    def test_accepts_paper_url(self) -> None:
        assert assert_paper_url(PAPER_TRADING_URL) == PAPER_TRADING_URL

    def test_accepts_paper_url_with_trailing_slash(self) -> None:
        assert assert_paper_url(PAPER_TRADING_URL + "/") == PAPER_TRADING_URL


class TestSettingsConstructionGuard:
    """The guard also runs when Settings loads, so a bad .env fails at startup."""

    @pytest.mark.parametrize("url", REJECTED_URLS)
    def test_settings_construction_refuses_non_paper_url(self, url: str) -> None:
        with pytest.raises(LiveTradingRefused):
            _settings(url)


class TestMakeTradingClient:
    @pytest.mark.parametrize("url", REJECTED_URLS)
    def test_refuses_before_any_network_call(self, url: str) -> None:
        """No setting disables the guard: every rejected URL is refused, and
        the SDK's TradingClient is never constructed (so no network call is
        even possible).
        """
        # Settings() itself already refuses a bad URL at load time (see
        # TestSettingsConstructionGuard), so build a valid Settings object
        # and then set the bad URL by plain attribute assignment (which
        # skips Settings' own validator) to prove make_trading_client's
        # *own* call to assert_paper_url, independent of Settings.
        settings = _settings(PAPER_TRADING_URL)
        settings.alpaca_base_url = url
        with (
            patch("bullpit.broker.clients.TradingClient") as mock_ctor,
            pytest.raises(LiveTradingRefused),
        ):
            make_trading_client(settings)
        mock_ctor.assert_not_called()

    def test_builds_paper_client_with_paper_true(self) -> None:
        settings = _settings(PAPER_TRADING_URL)
        mock_instance = MagicMock()
        with patch("bullpit.broker.clients.TradingClient", return_value=mock_instance) as mock_ctor:
            client = make_trading_client(settings)

        assert client is mock_instance
        mock_ctor.assert_called_once_with(
            api_key="fake-key",
            secret_key="fake-secret",
            paper=True,
            url_override=PAPER_TRADING_URL,
        )

    def test_builds_paper_client_with_trailing_slash_url(self) -> None:
        settings = _settings(PAPER_TRADING_URL)
        settings.alpaca_base_url = PAPER_TRADING_URL + "/"
        with patch("bullpit.broker.clients.TradingClient") as mock_ctor:
            make_trading_client(settings)

        mock_ctor.assert_called_once_with(
            api_key="fake-key",
            secret_key="fake-secret",
            paper=True,
            url_override=PAPER_TRADING_URL,
        )
