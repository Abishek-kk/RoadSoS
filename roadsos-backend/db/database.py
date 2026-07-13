# database.py — SQLite/PostgreSQL connection
from sqlalchemy import create_engine, inspect, text
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


def _upgrade_sqlite_schema():
    """Apply minimal schema upgrades for existing SQLite databases."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "users" not in existing_tables:
        return

    with engine.begin() as conn:
        existing_cols = {col["name"] for col in inspector.get_columns("users")}
        if "role" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(30) NOT NULL DEFAULT 'user'"))
        if "preferences" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN preferences TEXT NOT NULL DEFAULT '{}'"))
        if "is_active" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        if "is_admin" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
        if "firebase_token" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN firebase_token TEXT"))
        if "last_location_lat" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_location_lat FLOAT"))
        if "last_location_lng" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_location_lng FLOAT"))
        if "last_seen_at" not in existing_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_seen_at DATETIME"))

        if "emergency_contacts" in existing_tables:
            existing_cols = {col["name"] for col in inspector.get_columns("emergency_contacts")}
            if "created_at" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"))
            if "updated_at" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"))
            if "is_primary" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT 0"))
            if "priority" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN priority INTEGER NOT NULL DEFAULT 1"))
            if "notify_sms" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN notify_sms BOOLEAN NOT NULL DEFAULT 1"))
            if "notify_whatsapp" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN notify_whatsapp BOOLEAN NOT NULL DEFAULT 1"))
            if "notify_call" not in existing_cols:
                conn.execute(text("ALTER TABLE emergency_contacts ADD COLUMN notify_call BOOLEAN NOT NULL DEFAULT 0"))

        if "sos_events" in existing_tables:
            existing_cols = {col["name"] for col in inspector.get_columns("sos_events")}
            if "user_name" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN user_name VARCHAR(120)"))
            if "speed" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN speed FLOAT"))
            if "accuracy_m" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN accuracy_m FLOAT"))
            if "battery_percent" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN battery_percent INTEGER"))
            if "device_id" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN device_id VARCHAR(120)"))
            if "severity" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN severity VARCHAR(40) NOT NULL DEFAULT 'high'"))
            if "emergency_type" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN emergency_type VARCHAR(80)"))
            if "note" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN note TEXT"))
            if "notification_summary" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN notification_summary TEXT"))
            if "updated_at" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"))
            if "assigned_responder_id" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN assigned_responder_id VARCHAR(80)"))
            if "resolution_note" not in existing_cols:
                conn.execute(text("ALTER TABLE sos_events ADD COLUMN resolution_note TEXT"))

        if "location_logs" in existing_tables:
            existing_cols = {col["name"] for col in inspector.get_columns("location_logs")}
            if "device_id" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN device_id VARCHAR(120)"))
            if "heading" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN heading FLOAT"))
            if "accuracy_m" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN accuracy_m FLOAT"))
            if "altitude_m" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN altitude_m FLOAT"))
            if "source" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'unknown'"))
            if "battery_percent" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN battery_percent INTEGER"))
            if "is_mock_location" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN is_mock_location BOOLEAN NOT NULL DEFAULT 0"))
            if "recorded_at" not in existing_cols:
                conn.execute(text("ALTER TABLE location_logs ADD COLUMN recorded_at DATETIME"))

        if "push_subscriptions" not in existing_tables:
            conn.execute(text("""
                CREATE TABLE push_subscriptions (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    endpoint TEXT NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                    CONSTRAINT uq_push_subscriptions_endpoint UNIQUE (endpoint)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id ON push_subscriptions (user_id)"))


def init_db():
    """
    Initializes the database by creating all tables.
    Import models here to register them with the metadata.
    """
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _upgrade_sqlite_schema()
    from app.services.ambulance_service import seed_ambulances

    db = SessionLocal()
    try:
        seed_ambulances(db)
    finally:
        db.close()
