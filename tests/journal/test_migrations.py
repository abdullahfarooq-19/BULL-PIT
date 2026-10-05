"""`alembic upgrade head` produces a schema matching journal/models.py
(M4-AC-10): covers migrations 0001-0009 (M6-AC-9, M8-AC-9, M11.1-AC-15, M11.2-AC-13), and
`0008` keeps the rows a `0007` database holds (M11.1-AC-17c).

`env.py` always derives the target URL from `get_settings()` (M2 specs-plan
sec9.5: app and migrations share one path), not from the `Config` object,
so the DB path here is set through `JOURNAL_DB_PATH` and the settings
cache is cleared around the run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.autogenerate import compare_metadata
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from bullpit.config import get_settings
from bullpit.journal.db import journal_url
from bullpit.journal.models import Base

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "bullpit" / "journal" / "migrations"


class TestMigrationsMatchOrmMetadata:
    def test_upgrade_head_has_no_schema_diff(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "journal.db"
        monkeypatch.setenv("JOURNAL_DB_PATH", str(db_path))
        get_settings.cache_clear()
        try:
            cfg = AlembicConfig()
            cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
            alembic_command.upgrade(cfg, "head")

            engine = create_engine(journal_url(get_settings()))
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                diff = compare_metadata(context, Base.metadata)
            engine.dispose()
        finally:
            get_settings.cache_clear()

        assert diff == []


class TestZeroEightKeepsRows:
    def test_0008_keeps_existing_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JOURNAL_DB_PATH", str(tmp_path / "journal.db"))
        get_settings.cache_clear()
        try:
            cfg = AlembicConfig()
            cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
            alembic_command.upgrade(cfg, "0007")
            engine = create_engine(journal_url(get_settings()))
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO requests (id, mode, as_of, created_at, ticker, status) "
                        "VALUES ('r1', 'live', '2026-10-02', '2026-10-02 20:00:00', "
                        "'AAPL', 'completed')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO approvals (request_id, decision, recommended_shares, "
                        "approved_shares, decided_by, decided_at, latest_price, confirmations) "
                        "VALUES ('r1', 'approved', 32, 30, 'owner', '2026-10-02 20:05:00', "
                        "'182.40', '[\"stale\"]')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO trades (request_id, client_order_id, ticker, submitted_on, "
                        "shares, reference_price, stop_loss, take_profit, status, order_id) "
                        "VALUES ('r1', 'bullpit-r1', 'AAPL', '2026-10-02', 30, '182.00', "
                        "'174.00', '194.00', 'pending', 'abc')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO reports (request_id, report) "
                        "VALUES ('r1', '{\"ticker\": \"AAPL\"}')"
                    )
                )
            engine.dispose()

            alembic_command.upgrade(cfg, "0008")

            engine = create_engine(journal_url(get_settings()))
            with engine.connect() as connection:
                approval = connection.execute(text("SELECT * FROM approvals")).mappings().one()
                trade = connection.execute(text("SELECT * FROM trades")).mappings().one()
                report = connection.execute(text("SELECT report FROM reports")).scalar_one()
            engine.dispose()
        finally:
            get_settings.cache_clear()

        assert (approval["approved_shares"], approval["latest_price"]) == (30, "182.40")
        assert approval["confirmations"] == '["stale"]'
        assert approval["order_type"] == "market"
        for column in ("entry_price", "limit_price", "stop_loss", "take_profit", "seen_price"):
            assert approval[column] is None
        assert approval["overrides"] is None
        assert (trade["shares"], trade["reference_price"], trade["order_id"]) == (
            30,
            "182.00",
            "abc",
        )
        assert trade["order_type"] == "market"
        assert trade["limit_price"] is None
        assert report == '{"ticker": "AAPL"}'
