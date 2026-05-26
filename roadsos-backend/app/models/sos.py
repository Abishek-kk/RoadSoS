"""
sos.py - SOS event schemas.

Models for triggering, tracking, resolving, and returning RoadSoS emergency SOS
events. These schemas match the current /sos route while leaving room for DB
persistence and richer emergency workflow data.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class SOSStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    DISPATCHED = "dispatched"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"
    FALSE_ALARM = "false_alarm"


class SOSSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    SUBMITTED = "submitted"
    DRY_RUN = "dry_run"
    FAILED = "failed"
    SKIPPED = "skipped"


class SOSBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def empty_note_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class SOSCreate(SOSBase):
    user_id: int | None = Field(default=None, ge=1)
    user: str | None = Field(default=None, max_length=120)
    severity: SOSSeverity = SOSSeverity.HIGH
    emergency_type: str | None = Field(default=None, max_length=80)
    speed: float | None = Field(default=None, ge=0)
    accuracy_m: float | None = Field(default=None, ge=0)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    device_id: str | None = Field(default=None, max_length=120)

    @computed_field
    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.lat},{self.lng}"


class SOSUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    status: SOSStatus | None = None
    severity: SOSSeverity | None = None
    note: str | None = Field(default=None, max_length=500)
    danger_zone_id: str | None = None
    nearest_hospital_id: str | None = None
    nearest_police_id: str | None = None
    assigned_responder_id: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = Field(default=None, max_length=500)

    _empty_note_to_none = field_validator("note", "resolution_note", mode="before")(SOSBase.empty_note_to_none)


class NotificationResultResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    contact_name: str
    phone: str
    channel: str = "whatsapp"
    status: NotificationStatus | str
    sid: str | None = None
    error: str | None = None


class SOSNotificationSummary(BaseModel):
    contacts: int = Field(0, ge=0)
    sent: int = Field(0, ge=0)
    dry_run: int = Field(0, ge=0)
    failed: int = Field(0, ge=0)
    results: list[NotificationResultResponse] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_counts_from_results(self) -> "SOSNotificationSummary":
        if self.results and not self.contacts:
            self.contacts = len(self.results)
        if self.results and not any([self.sent, self.dry_run, self.failed]):
            sent_statuses = {"accepted", "queued", "sending", "sent", "submitted"}
            self.sent = sum(1 for item in self.results if str(item.status) in sent_statuses)
            self.dry_run = sum(1 for item in self.results if str(item.status) == "dry_run")
            self.failed = sum(1 for item in self.results if str(item.status) == "failed")
        return self


class SOSResponse(SOSBase):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, use_enum_values=True)

    id: int | str
    sos_id: str | None = None
    user_id: int | None = None
    user: str | None = None
    status: SOSStatus | str = SOSStatus.ACTIVE
    severity: SOSSeverity | str = SOSSeverity.HIGH
    emergency_type: str | None = None
    danger_zone_id: str | None = None
    nearest_hospital_id: str | None = None
    nearest_police_id: str | None = None
    assigned_responder_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    notifications: SOSNotificationSummary | None = None

    @computed_field
    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.lat},{self.lng}"

    @model_validator(mode="after")
    def validate_resolution(self) -> "SOSResponse":
        if self.resolved_at and self.resolved_at < self.created_at:
            raise ValueError("resolved_at cannot be before created_at")
        if self.updated_at and self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        if self.sos_id is None:
            self.sos_id = str(self.id)
        return self


class SOSTriggerResponse(BaseModel):
    ok: bool = True
    sos_id: str
    status: SOSStatus | str = SOSStatus.ACTIVE
    received: SOSCreate
    notifications: SOSNotificationSummary


class SOSListResponse(BaseModel):
    events: list[SOSResponse] = Field(default_factory=list)
    count: int | None = None

    @model_validator(mode="after")
    def fill_count(self) -> "SOSListResponse":
        if self.count is None:
            self.count = len(self.events)
        return self


class SOSResolveRequest(BaseModel):
    status: SOSStatus = SOSStatus.RESOLVED
    resolved_at: datetime = Field(default_factory=datetime.now)
    resolution_note: str | None = Field(default=None, max_length=500)

    @field_validator("status")
    @classmethod
    def status_must_close_event(cls, value: SOSStatus) -> SOSStatus:
        if value not in {SOSStatus.RESOLVED, SOSStatus.CANCELLED, SOSStatus.FALSE_ALARM}:
            raise ValueError("resolve request status must be resolved, cancelled, or false_alarm")
        return value
