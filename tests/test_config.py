"""Settings defaults match the architecture's values (M4-AC-15)."""

from __future__ import annotations

from decimal import Decimal

from bullpit.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


class TestM4SettingDefaults:
    def test_debate_defaults(self) -> None:
        settings = _settings()
        assert settings.debate_rounds == 2
        assert settings.debate_turn_max_words == 150

    def test_risk_defaults(self) -> None:
        settings = _settings()
        assert settings.risk_per_trade_pct == Decimal("0.01")
        assert settings.max_position_pct == Decimal("0.10")
        assert settings.risk_max_vetoes == 2
        assert settings.loss_warning_pct == Decimal("0.05")
        assert settings.loss_warning_days == 7

    def test_exit_table_defaults(self) -> None:
        settings = _settings()
        assert settings.exit_stop_atr_tight == Decimal("1.5")
        assert settings.exit_stop_atr_normal == Decimal("2")
        assert settings.exit_stop_atr_wide == Decimal("3")
        assert settings.exit_reward_risk == Decimal("1.5")


class TestM5SettingDefaults:
    def test_vix_thresholds(self) -> None:
        settings = _settings()
        assert settings.vix_low_threshold == 15.0
        assert settings.vix_high_threshold == 25.0


class TestM6SettingDefaults:
    def test_backtest_defaults(self) -> None:
        settings = _settings()
        assert settings.sim_slippage_pct == Decimal("0.0005")
        assert settings.backtest_starting_cash == Decimal("100000")
        assert settings.backtest_weeks == 26


class TestM7SettingDefaults:
    def test_evaluation_defaults(self) -> None:
        settings = _settings()
        assert settings.baseline_target_weight == Decimal("0.06")
        assert settings.baseline_exit_style == "normal"
        assert settings.eval_calibration_bins == 5
        assert settings.llm_provider == "groq"
