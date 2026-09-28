"""SQLite engine and session factory for the journal (M2 specs-plan sec9.5).

`journal.db` (or `sqlite://` in memory, for tests) holds the structured,
queryable rows every milestone's `journal/models.py` additions build on.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings


def journal_url(settings: Settings) -> str:
    return f"sqlite:///{settings.journal_db_path}"


def make_engine(url: str) -> Engine:
    """`create_engine(url)`, with WAL mode and foreign keys on for every
    connection the pool opens (dev-plan.md sec8; M2 specs-plan sec9.5).
    """
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
