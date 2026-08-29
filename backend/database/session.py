from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "postgresql://postgres:Akoth2006@localhost:5432/reflex_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

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