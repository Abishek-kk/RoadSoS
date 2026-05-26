# database.py — SQLite/PostgreSQL connection
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

# Conditional arguments: check_same_thread is only required and supported for SQLite
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

# Create engine with optional connection arguments
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Create local session class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base class for models
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a transactional database session.
    Automatically closes the session after the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initializes the database by creating all tables.
    Import models here to register them with the metadata.
    """
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
