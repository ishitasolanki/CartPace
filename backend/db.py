"""SQLAlchemy engine and session.

SQLite, per project.md section 14: single clinic, single device, no
concurrent writers. Postgres is out of scope until a second real deployment
needs it (project.md section 16).
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).resolve().parents[1] / 'cartpace.db'}",
)

# check_same_thread=False: FastAPI may serve a request on a different thread
# than the one that created the connection. Safe here because SQLite access
# is single-writer and requests are short-lived; not a concurrency licence.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    from backend import models  # noqa: F401  (registers tables on Base)

    Base.metadata.create_all(bind=engine)
