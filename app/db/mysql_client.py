from typing import Any, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# pool_pre_ping=True: verifies the connection is alive before each use —
# prevents "MySQL server has gone away" errors on long-idle containers.
engine = create_engine(
    settings.ai_db_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Dependency / context manager
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    Yields a SQLAlchemy Session and guarantees close on exit.
    Intended for use as a FastAPI Depends() or a plain context manager.

    Usage in a service (not in a router):
        with next(get_db()) as db:  # or just call get_db() directly
            rows = db.execute(text("SELECT ...")).fetchall()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """
    Execute a raw SELECT and return a list of dicts (column → value).
    Use for read-only analytics queries where an ORM model is overkill.
    """
    with SessionLocal() as db:
        result = db.execute(text(sql), params or {})
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]


def execute_write(sql: str, params: dict[str, Any] | None = None) -> int:
    """
    Execute a single INSERT / UPDATE / DELETE and return rowcount.
    Commits automatically on success; rolls back on any exception.
    """
    with SessionLocal() as db:
        result = db.execute(text(sql), params or {})
        db.commit()
        return result.rowcount
