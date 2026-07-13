"""
models.py - SQLAlchemy ORM models for RoadSoS.

The table names and core model names remain compatible with db/crud.py while
the schema includes the richer fields used by the Pydantic app models.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.database import Base


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("last_location_lat IS NULL OR (last_location_lat >= -90 AND last_location_lat <= 90)"),
        CheckConstraint("last_location_lng IS NULL OR (last_location_lng >= -180 AND last_location_lng <= 180)"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=False)
    email = Column(String(254), unique=True, index=True, nullable=True)
    firebase_token = Column(Text, nullable=True)
    role = Column(String(30), nullable=False, default="user", server_default="user")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    is_admin = Column(Boolean, nullable=False, default=False, server_default="0")
    preferences = Column(JSON, nullable=False, default=dict)
    last_location_lat = Column(Float, nullable=True)
    last_location_lng = Column(Float, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    contacts = relationship(
        "EmergencyContact",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EmergencyContact.priority",
    )
    sos_events = relationship("SOSEvent", back_populates="user", passive_deletes=True)
    location_logs = relationship(
        "LocationLog",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    push_subscriptions = relationship(
        "PushSubscription",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    danger_zone_alert_events = relationship(
        "DangerZoneAlertEvent",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} phone={self.phone!r}>"


class EmergencyContact(Base, TimestampMixin):
    __tablename__ = "emergency_contacts"
    __table_args__ = (
        UniqueConstraint("user_id", "phone", name="uq_emergency_contact_user_phone"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(20), nullable=False)
    relation = Column(String(40), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False, server_default="0")
    priority = Column(Integer, nullable=False, default=1, server_default="1")
    notify_sms = Column(Boolean, nullable=False, default=True, server_default="1")
    notify_whatsapp = Column(Boolean, nullable=False, default=True, server_default="1")
    notify_call = Column(Boolean, nullable=False, default=False, server_default="0")

    user = relationship("User", back_populates="contacts")

    def __repr__(self) -> str:
        return f"<EmergencyContact id={self.id!r} user_id={self.user_id!r} phone={self.phone!r}>"


class SOSEvent(Base):
    __tablename__ = "sos_events"
    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90"),
        CheckConstraint("lng >= -180 AND lng <= 180"),
        Index("ix_sos_events_status_created_at", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_name = Column(String(120), nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    accuracy_m = Column(Float, nullable=True)
    battery_percent = Column(Integer, nullable=True)
    device_id = Column(String(120), nullable=True)
    status = Column(String(40), nullable=False, default="active", server_default="active")
    severity = Column(String(40), nullable=False, default="high", server_default="high")
    emergency_type = Column(String(80), nullable=True)
    note = Column(Text, nullable=True)
    danger_zone_id = Column(String(80), nullable=True, index=True)
    nearest_hospital_id = Column(String(80), nullable=True)
    nearest_police_id = Column(String(80), nullable=True)
    assigned_responder_id = Column(String(80), nullable=True)
    notification_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)

    user = relationship("User", back_populates="sos_events")
    notifications = relationship(
        "NotificationDelivery",
        back_populates="sos_event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<SOSEvent id={self.id!r} status={self.status!r}>"


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_notification_deliveries_sos_status", "sos_event_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sos_event_id = Column(Integer, ForeignKey("sos_events.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id = Column(Integer, ForeignKey("emergency_contacts.id", ondelete="SET NULL"), nullable=True)
    contact_name = Column(String(120), nullable=False)
    phone = Column(String(20), nullable=False)
    channel = Column(String(30), nullable=False, default="whatsapp", server_default="whatsapp")
    status = Column(String(40), nullable=False)
    sid = Column(String(120), nullable=True)
    error = Column(Text, nullable=True)
    provider_response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sos_event = relationship("SOSEvent", back_populates="notifications")
    contact = relationship("EmergencyContact")


class PushSubscription(Base, TimestampMixin):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)

    user = relationship("User", back_populates="push_subscriptions")


class LocationLog(Base):
    __tablename__ = "location_logs"
    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90"),
        CheckConstraint("lng >= -180 AND lng <= 180"),
        CheckConstraint("speed IS NULL OR speed >= 0"),
        Index("ix_location_logs_user_timestamp", "user_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    device_id = Column(String(120), nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    speed = Column(Float, default=0.0, server_default="0")
    heading = Column(Float, nullable=True)
    accuracy_m = Column(Float, nullable=True)
    altitude_m = Column(Float, nullable=True)
    source = Column(String(30), nullable=False, default="unknown", server_default="unknown")
    battery_percent = Column(Integer, nullable=True)
    is_mock_location = Column(Boolean, nullable=False, default=False, server_default="0")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="location_logs")

    def __repr__(self) -> str:
        return f"<LocationLog id={self.id!r} user_id={self.user_id!r} lat={self.lat!r} lng={self.lng!r}>"


class Ambulance(Base):
    __tablename__ = "ambulances"
    __table_args__ = (
        CheckConstraint("lat IS NULL OR (lat >= -90 AND lat <= 90)"),
        CheckConstraint("lng IS NULL OR (lng >= -180 AND lng <= 180)"),
        CheckConstraint("status IN ('available', 'busy')"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ambulance_id = Column(String(40), unique=True, nullable=False, index=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    phone = Column(String(20), nullable=True)
    distance_km = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="available", server_default="available")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Ambulance ambulance_id={self.ambulance_id!r} status={self.status!r}>"


class RoadAlert(Base):
    __tablename__ = "road_alerts"
    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90"),
        CheckConstraint("lng >= -180 AND lng <= 180"),
        CheckConstraint("lanes_blocked >= 0"),
        CheckConstraint("total_lanes >= 1"),
        Index("ix_road_alerts_status_severity", "status", "severity"),
        Index("ix_road_alerts_location", "lat", "lng"),
    )

    id = Column(String(80), primary_key=True, index=True)
    title = Column(String(160), nullable=False)
    type = Column(String(40), nullable=False, index=True)
    severity = Column(String(40), nullable=False, index=True)
    status = Column(String(40), nullable=False, default="active", server_default="active", index=True)
    description = Column(Text, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(120), nullable=False, index=True)
    state = Column(String(120), nullable=False, index=True)
    road = Column(String(120), nullable=False, index=True)
    direction = Column(String(120), nullable=False)
    lanes_blocked = Column(Integer, nullable=False, default=0, server_default="0")
    total_lanes = Column(Integer, nullable=False, default=1, server_default="1")
    vehicles_involved = Column(Integer, nullable=False, default=0, server_default="0")
    casualties = Column(Integer, nullable=False, default=0, server_default="0")
    injuries = Column(Integer, nullable=False, default=0, server_default="0")
    reported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    estimated_clearance = Column(DateTime(timezone=True), nullable=True)
    nearest_hospital_id = Column(String(80), nullable=True)
    nearest_police_id = Column(String(80), nullable=True)
    detour = Column(Text, nullable=True)
    source = Column(String(120), nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    raw_payload = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<RoadAlert id={self.id!r} severity={self.severity!r} status={self.status!r}>"


class DangerZone(Base):
    __tablename__ = "danger_zones"
    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90"),
        CheckConstraint("lng >= -180 AND lng <= 180"),
        CheckConstraint("radius_km >= 0"),
        Index("ix_danger_zones_location", "lat", "lng"),
    )

    id = Column(String(80), primary_key=True, index=True)
    name = Column(String(160), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    radius_km = Column(Float, nullable=False, default=1.0, server_default="1")
    risk_level = Column(String(40), nullable=False, index=True)
    risk_score = Column(Float, nullable=False, default=0.0, server_default="0")
    city = Column(String(120), nullable=True, index=True)
    state = Column(String(120), nullable=True, index=True)
    road = Column(String(120), nullable=True, index=True)
    type = Column(String(80), nullable=True)
    primary_causes = Column(JSON, nullable=False, default=list)
    accident_history = Column(JSON, nullable=False, default=dict)
    peak_risk_hours = Column(JSON, nullable=False, default=list)
    weather_sensitivity = Column(JSON, nullable=False, default=list)
    advisory = Column(Text, nullable=True)
    reported_by = Column(String(160), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<DangerZone id={self.id!r} risk_level={self.risk_level!r}>"


class DangerZoneAlertEvent(Base):
    __tablename__ = "danger_zone_alert_events"
    __table_args__ = (
        CheckConstraint("lat >= -90 AND lat <= 90"),
        CheckConstraint("lng >= -180 AND lng <= 180"),
        Index("ix_dz_alert_events_user_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    zone_id = Column(String(80), nullable=False, index=True)
    zone_name = Column(String(160), nullable=False)
    risk_level = Column(String(40), nullable=False)
    risk_score = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    inside_zone = Column(Boolean, nullable=False, default=False, server_default="0")
    message = Column(Text, nullable=True)
    advisory = Column(Text, nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    notified_push = Column(Boolean, nullable=False, default=False, server_default="0")
    notified_sms = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    user = relationship("User", back_populates="danger_zone_alert_events")

    def __repr__(self) -> str:
        return f"<DangerZoneAlertEvent id={self.id!r} user_id={self.user_id!r} zone_id={self.zone_id!r}>"
