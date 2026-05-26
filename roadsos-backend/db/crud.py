# crud.py — DB read/write operations
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime
from typing import List, Optional
from db import models
from app.models import user as user_schema, sos as sos_schema, location as location_schema

# -------------------------------------------------------------------
# User CRUD Operations
# -------------------------------------------------------------------

def get_user(db: Session, user_id: int) -> Optional[models.User]:
    """Retrieve a user by their unique database ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    """Retrieve a user by their unique phone number."""
    return db.query(models.User).filter(models.User.phone == phone).first()


def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[models.User]:
    """Retrieve a list of users with pagination."""
    return db.query(models.User).offset(skip).limit(limit).all()


def create_user(db: Session, user: user_schema.UserCreate) -> models.User:
    """Create a new user in the database."""
    db_user = models.User(
        name=user.name,
        phone=user.phone,
        email=user.email,
        firebase_token=user.firebase_token
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user_update: user_schema.UserUpdate) -> Optional[models.User]:
    """Update user information (e.g. name, email, firebase_token)."""
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    """Delete a user and their cascaded relations."""
    db_user = get_user(db, user_id)
    if not db_user:
        return False
    db.delete(db_user)
    db.commit()
    return True

# -------------------------------------------------------------------
# Emergency Contact CRUD Operations
# -------------------------------------------------------------------

def get_emergency_contacts(db: Session, user_id: int) -> List[models.EmergencyContact]:
    """Retrieve all emergency contacts associated with a user."""
    return db.query(models.EmergencyContact).filter(models.EmergencyContact.user_id == user_id).all()


def create_emergency_contact(db: Session, contact: user_schema.ContactCreate, user_id: int) -> models.EmergencyContact:
    """Add a new emergency contact for a user."""
    db_contact = models.EmergencyContact(
        user_id=user_id,
        name=contact.name,
        phone=contact.phone,
        relation=contact.relation
    )
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def delete_emergency_contact(db: Session, contact_id: int) -> bool:
    """Remove an emergency contact."""
    db_contact = db.query(models.EmergencyContact).filter(models.EmergencyContact.id == contact_id).first()
    if not db_contact:
        return False
    db.delete(db_contact)
    db.commit()
    return True

# -------------------------------------------------------------------
# SOS Event CRUD Operations
# -------------------------------------------------------------------

def get_sos_event(db: Session, sos_id: int) -> Optional[models.SOSEvent]:
    """Retrieve a single SOS event by its ID."""
    return db.query(models.SOSEvent).filter(models.SOSEvent.id == sos_id).first()


def get_active_sos_events(db: Session) -> List[models.SOSEvent]:
    """Retrieve all ongoing/unresolved SOS events."""
    return db.query(models.SOSEvent).filter(models.SOSEvent.status == "active").all()


def get_user_sos_history(db: Session, user_id: int) -> List[models.SOSEvent]:
    """Retrieve all past and active SOS events for a specific user."""
    return db.query(models.SOSEvent).filter(models.SOSEvent.user_id == user_id).order_by(desc(models.SOSEvent.created_at)).all()


def create_sos_event(
    db: Session,
    sos: sos_schema.SOSCreate,
    danger_zone_id: Optional[str] = None,
    nearest_hospital_id: Optional[str] = None,
    nearest_police_id: Optional[str] = None
) -> models.SOSEvent:
    """Record a new active SOS event in the system."""
    db_sos = models.SOSEvent(
        user_id=sos.user_id,
        lat=sos.lat,
        lng=sos.lng,
        status="active",
        danger_zone_id=danger_zone_id,
        nearest_hospital_id=nearest_hospital_id,
        nearest_police_id=nearest_police_id
    )
    db.add(db_sos)
    db.commit()
    db.refresh(db_sos)
    return db_sos


def resolve_sos_event(db: Session, sos_id: int) -> Optional[models.SOSEvent]:
    """Mark an active SOS event as resolved/completed."""
    db_sos = get_sos_event(db, sos_id)
    if not db_sos or db_sos.status == "resolved":
        return db_sos
    
    db_sos.status = "resolved"
    db_sos.resolved_at = datetime.now()
    db.commit()
    db.refresh(db_sos)
    return db_sos

# -------------------------------------------------------------------
# Location Log CRUD Operations
# -------------------------------------------------------------------

def create_location_log(db: Session, location: location_schema.LocationCreate) -> models.LocationLog:
    """Log a user's current GPS location and speed for history tracking."""
    db_log = models.LocationLog(
        user_id=location.user_id,
        lat=location.lat,
        lng=location.lng,
        speed=location.speed
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_user_location_history(db: Session, user_id: int, limit: int = 50) -> List[models.LocationLog]:
    """Retrieve GPS log history for a specific user, sorted from newest to oldest."""
    return db.query(models.LocationLog)\
        .filter(models.LocationLog.user_id == user_id)\
        .order_by(desc(models.LocationLog.timestamp))\
        .limit(limit)\
        .all()


def get_latest_user_location(db: Session, user_id: int) -> Optional[models.LocationLog]:
    """Get the most recent location update for a user."""
    return db.query(models.LocationLog)\
        .filter(models.LocationLog.user_id == user_id)\
        .order_by(desc(models.LocationLog.timestamp))\
        .first()
