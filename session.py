from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQLite database URL pointing to a local reflex.db file
SQLALCHEMY_DATABASE_URL = "sqlite:///./reflex.db"

# Create the SQLAlchemy engine
# 'check_same_thread': False is needed only for SQLite to allow multiple threads in FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
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
