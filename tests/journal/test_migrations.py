"""`alembic upgrade head` produces a schema matching journal/models.py
(M4-AC-10): covers migrations 0001-0005 (M6-AC-9).

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
from sqlalchemy import create_engine

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
