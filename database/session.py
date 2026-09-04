import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database URL is read from the environment so the exact same code works
# locally (SQLite today, or local Postgres) and in production (hosted
# Postgres on Render). Falls back to the existing SQLite file if
# DATABASE_URL isn't set, so nothing breaks before you've set it.
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./reflex.db",
)

# 'check_same_thread' is only needed for SQLite, to allow multiple
# threads in FastAPI. Postgres doesn't need (or accept) this argument.
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Create the SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
)

# Create a SessionLocal factory to generate database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    """
    Dependency generator for FastAPI endpoints.
    Yields a database session per request and closes it after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()