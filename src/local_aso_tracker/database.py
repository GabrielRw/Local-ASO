"""Database engine, sessions, and Alembic migration helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from local_aso_tracker.config import database_path


def create_db_engine(path: Path | None = None) -> Engine:
    """Create a SQLite engine with safe local defaults."""

    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{target}", future=True)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Provide a transactional session that commits or rolls back."""

    owned_engine = engine or create_db_engine()
    factory = sessionmaker(owned_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_migrations(path: Path | None = None) -> None:
    """Upgrade the configured local database to the latest schema."""

    root = Path(__file__).resolve().parents[2]
    config = Config(root / "alembic.ini")
    db = path or database_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(config, "head")
