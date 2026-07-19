"""
database.py — SQLAlchemy engine/session setup.

Provides:
- Base: the declarative base every model in backend/models/ inherits from
- engine: SQLite engine bound to data/tasks.db
- SessionLocal: session factory
- get_db(): FastAPI dependency that yields a session and closes it after use
- init_db(): creates all tables — call once on app startup

The import of backend.models inside init_db() is deliberately lazy: it
registers every model class on Base.metadata without database.py having
to import models/ at module load time (which would be circular, since
every model imports Base from here).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend import config


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


engine = create_engine(
    config.DATABASE_URL,
    echo=config.SQL_ECHO,
    # Needed for SQLite when accessed from multiple threads (FastAPI + APScheduler).
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI dependency: yields a session, guarantees it's closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables that don't exist yet. Safe to call every startup."""
    from backend import models  # noqa: F401  (registers models on Base.metadata)
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    # `python -m backend.database` — quick manual sanity check.
    init_db()
    print(f"Initialized database at {config.DB_PATH}")
