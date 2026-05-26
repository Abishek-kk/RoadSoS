"""
alert.py - road alert schemas.

These Pydantic models describe RoadSoS traffic, hazard, weather, construction,
and accident alerts. They match data/road_alerts.json while also supporting the
flattened fields returned by the alerts API.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AlertType(StrEnum):
    ACCIDENT = "accident"
    WEATHER = "weather"
    CONSTRUCTION = "construction"
    BREAKDOWN = "breakdown"
    CHECKPOINT = "checkpoint"
    HAZARD = "hazard"
    RESTRICTION = "restriction"
    VIP_MOVEMENT = "vip_movement"
    ROAD_DAMAGE = "road_damage"
    TRAFFIC = "traffic"
    OBSTRUCTION = "obstruction"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    ACTIVE = "active"
    OPEN = "open"
    ONGOING = "ongoing"
    RESOLVED = "resolved"
    CLOSED = "closed"
    UNDER_INVESTIGATION = "under_investigation"


class LocationDetails(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    address: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    state: str = Field(..., min_length=1)


class AlertBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    title: str = Field(..., min_length=3, max_length=160)
    type: AlertType
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.ACTIVE
    description: str = Field(..., min_length=5)
    location: LocationDetails
    road: str = Field(..., min_length=1, max_length=120)
    direction: str = Field(..., min_length=1, max_length=120)
    lanes_blocked: int = Field(0, ge=0)
    total_lanes: int = Field(1, ge=1)
    vehicles_involved: int = Field(0, ge=0)
    casualties: int = Field(0, ge=0)
    injuries: int = Field(0, ge=0)
    reported_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    estimated_clearance: datetime | None = None
    nearest_hospital_id: str | None = None
    nearest_police_id: str | None = None
    detour: str | None = None
    source: str = Field(..., min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",")]
        return sorted({str(item).strip().lower() for item in value if str(item).strip()})

    @field_validator("nearest_hospital_id", "nearest_police_id", "detour", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_lanes_and_times(self) -> "AlertBase":
        if self.lanes_blocked > self.total_lanes:
            raise ValueError("lanes_blocked cannot be greater than total_lanes")
        if self.estimated_clearance and self.estimated_clearance < self.reported_at:
            raise ValueError("estimated_clearance cannot be before reported_at")
        if self.updated_at < self.reported_at:
            raise ValueError("updated_at cannot be before reported_at")
        return self


class AlertCreate(AlertBase):
    """Payload for creating/reporting a new road alert."""


class AlertUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    title: str | None = Field(default=None, min_length=3, max_length=160)
    type: AlertType | None = None
    severity: AlertSeverity | None = None
    status: AlertStatus | None = None
    description: str | None = Field(default=None, min_length=5)
    location: LocationDetails | None = None
    road: str | None = Field(default=None, min_length=1, max_length=120)
    direction: str | None = Field(default=None, min_length=1, max_length=120)
    lanes_blocked: int | None = Field(default=None, ge=0)
    total_lanes: int | None = Field(default=None, ge=1)
    vehicles_involved: int | None = Field(default=None, ge=0)
    casualties: int | None = Field(default=None, ge=0)
    injuries: int | None = Field(default=None, ge=0)
    updated_at: datetime | None = None
    estimated_clearance: datetime | None = None
    nearest_hospital_id: str | None = None
    nearest_police_id: str | None = None
    detour: str | None = None
    source: str | None = Field(default=None, min_length=1, max_length=120)
    tags: list[str] | None = None

    _normalize_tags = field_validator("tags", mode="before")(AlertBase.normalize_tags)
    _empty_string_to_none = field_validator(
        "nearest_hospital_id",
        "nearest_police_id",
        "detour",
        mode="before",
    )(AlertBase.empty_string_to_none)


class AlertResponse(AlertBase):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, use_enum_values=True)

    id: str
    distance_km: float | None = None
    message: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    created_at: datetime | None = None

    @model_validator(mode="after")
    def fill_flattened_fields(self) -> "AlertResponse":
        if self.message is None:
            self.message = self.description
        if self.lat is None:
            self.lat = self.location.lat
        if self.lng is None:
            self.lng = self.location.lng
        if self.created_at is None:
            self.created_at = self.reported_at
        return self


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse] = Field(default_factory=list)
    count: int | None = None

    @model_validator(mode="after")
    def fill_count(self) -> "AlertListResponse":
        if self.count is None:
            self.count = len(self.alerts)
        return self


class AlertSummary(BaseModel):
    id: str
    title: str
    type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    road: str
    city: str
    state: str
    distance_km: float | None = None
    message: str

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
