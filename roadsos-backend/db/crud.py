# crud.py — DB read/write operations
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import UTC, datetime, timedelta
from typing import List, Optional
from app.config import get_danger_zone_sms_cooldown_minutes
from db import models
from app.models import user as user_schema, sos as sos_schema, location as location_schema

# -------------------------------------------------------------------
# User CRUD Operations
# -------------------------------------------------------------------

def get_user(db: Session, user_id: int) -> Optional[models.User]:
    """Retrieve a user by their unique database ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()


DEFAULT_SYSTEM_USER_PHONE = "+10000000000"


def get_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    """Retrieve a user by their unique phone number."""
    return db.query(models.User).filter(models.User.phone == phone).first()


def get_system_user(db: Session) -> Optional[models.User]:
    """Retrieve the shared RoadSoS system user used for anonymous contact persistence."""
    return get_user_by_phone(db, DEFAULT_SYSTEM_USER_PHONE)


def get_or_create_system_user(db: Session) -> models.User:
    """Get or create the shared RoadSoS system user for anonymous persistence."""
    user = get_system_user(db)
    if user:
        return user

    default_user = user_schema.UserCreate(
        name="RoadSoS User",
        phone=DEFAULT_SYSTEM_USER_PHONE,
        email=None,
        firebase_token=None,
    )
    return create_user(db, default_user)


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
        relation=contact.relation,
        is_primary=contact.is_primary,
        priority=contact.priority,
        notify_sms=contact.notify_sms,
        notify_whatsapp=contact.notify_whatsapp,
        notify_call=contact.notify_call,
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
        user_name=sos.user,
        lat=sos.lat,
        lng=sos.lng,
        speed=sos.speed,
        accuracy_m=sos.accuracy_m,
        battery_percent=sos.battery_percent,
        device_id=sos.device_id,
        status="active",
        severity=str(sos.severity),
        emergency_type=sos.emergency_type,
        note=sos.note,
        danger_zone_id=danger_zone_id,
        nearest_hospital_id=nearest_hospital_id,
        nearest_police_id=nearest_police_id,
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
        device_id=location.device_id,
        lat=location.lat,
        lng=location.lng,
        speed=location.speed,
        heading=location.heading,
        accuracy_m=location.accuracy_m,
        altitude_m=location.altitude_m,
        source=str(location.source),
        battery_percent=location.battery_percent,
        is_mock_location=location.is_mock_location,
        recorded_at=location.recorded_at,
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


# -------------------------------------------------------------------
# Danger Zone Alert Event CRUD Operations
# -------------------------------------------------------------------

def log_danger_zone_alert_event(
    db: Session,
    user_id: int,
    alert: dict,
    lat: float,
    lng: float,
    notified_push: bool = False,
    notified_sms: bool = False,
) -> models.DangerZoneAlertEvent:
    """Persist one danger-zone proximity event, deduped by user/zone cooldown."""
    zone_id = str(alert.get("zone_id") or alert.get("id") or "").strip()
    if not zone_id:
        raise ValueError("danger-zone alert event requires zone_id")

    existing = (
        db.query(models.DangerZoneAlertEvent)
        .filter(
            models.DangerZoneAlertEvent.user_id == user_id,
            models.DangerZoneAlertEvent.zone_id == zone_id,
        )
        .order_by(desc(models.DangerZoneAlertEvent.created_at))
        .first()
    )
    if existing and _is_within_danger_zone_cooldown(existing.created_at):
        return existing

    event = models.DangerZoneAlertEvent(
        user_id=user_id,
        zone_id=zone_id,
        zone_name=str(alert.get("zone_name") or alert.get("name") or zone_id),
        risk_level=str(alert.get("risk_level") or "unknown"),
        risk_score=alert.get("risk_score"),
        distance_km=alert.get("distance_km"),
        inside_zone=bool(alert.get("inside_zone")),
        message=alert.get("message"),
        advisory=alert.get("advisory"),
        lat=lat,
        lng=lng,
        notified_push=notified_push,
        notified_sms=notified_sms,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_recent_danger_zone_alerts(
    db: Session,
    user_id: int,
    limit: int = 20,
) -> List[models.DangerZoneAlertEvent]:
    """Retrieve recent persisted danger-zone proximity events for a user."""
    return (
        db.query(models.DangerZoneAlertEvent)
        .filter(models.DangerZoneAlertEvent.user_id == user_id)
        .order_by(desc(models.DangerZoneAlertEvent.created_at))
        .limit(limit)
        .all()
    )


def _is_within_danger_zone_cooldown(created_at: datetime | None) -> bool:
    if not created_at:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - created_at <= timedelta(minutes=get_danger_zone_sms_cooldown_minutes())


# -------------------------------------------------------------------
# Push Subscription CRUD Operations
# -------------------------------------------------------------------

def upsert_push_subscription(
    db: Session,
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> models.PushSubscription:
    subscription = (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.endpoint == endpoint)
        .first()
    )
    if subscription:
        subscription.user_id = user_id
        subscription.p256dh = p256dh
        subscription.auth = auth
    else:
        subscription = models.PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        db.add(subscription)

    db.commit()
    db.refresh(subscription)
    return subscription


def delete_push_subscription(db: Session, user_id: int, endpoint: str) -> bool:
    subscription = (
        db.query(models.PushSubscription)
        .filter(
            models.PushSubscription.user_id == user_id,
            models.PushSubscription.endpoint == endpoint,
        )
        .first()
    )
    if not subscription:
        return False
    db.delete(subscription)
    db.commit()
    return True


def get_push_subscriptions(db: Session, user_id: int) -> List[models.PushSubscription]:
    return (
        db.query(models.PushSubscription)
        .filter(models.PushSubscription.user_id == user_id)
        .order_by(desc(models.PushSubscription.created_at))
        .all()
    )
