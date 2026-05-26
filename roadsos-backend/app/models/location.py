"""
location.py - GPS payload and location log schemas.

These models validate user/device coordinates and optional movement telemetry
such as speed, heading, accuracy, altitude, and battery level.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LocationSource(StrEnum):
    GPS = "gps"
    NETWORK = "network"
    FUSED = "fused"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class LocationBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    speed: float | None = Field(default=0.0, ge=0, description="Speed in km/h")
    heading: float | None = Field(default=None, ge=0, lt=360, description="Bearing in degrees")
    accuracy_m: float | None = Field(default=None, ge=0, description="GPS accuracy radius in meters")
    altitude_m: float | None = Field(default=None, description="Altitude in meters")
    source: LocationSource = LocationSource.UNKNOWN
    recorded_at: datetime | None = None

    @field_validator("speed", mode="before")
    @classmethod
    def blank_speed_to_zero(cls, value: Any) -> Any:
        if value is None or value == "":
            return 0.0
        return value

    @model_validator(mode="after")
    def normalize_recorded_at(self) -> "LocationBase":
        if self.recorded_at is None:
            self.recorded_at = datetime.now()
        return self


class LocationCreate(LocationBase):
    user_id: int | None = Field(default=None, ge=1)
    device_id: str | None = Field(default=None, max_length=120)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    is_mock_location: bool = False


class LocationUpdate(LocationBase):
    """Alias used by clients that send periodic location updates."""

    user_id: int | None = Field(default=None, ge=1)
    device_id: str | None = Field(default=None, max_length=120)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    is_mock_location: bool = False


class LocationLogResponse(LocationBase):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, use_enum_values=True)

    id: int
    user_id: int | None = None
    device_id: str | None = None
    battery_percent: int | None = None
    is_mock_location: bool = False
    timestamp: datetime | None = None

    @model_validator(mode="after")
    def fill_timestamp(self) -> "LocationLogResponse":
        if self.timestamp is None:
            self.timestamp = self.recorded_at
        return self


class LocationResponse(BaseModel):
    ok: bool = True
    location: LocationCreate | LocationLogResponse


class LocationQuery(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=10.0, gt=0, le=200)

    @model_validator(mode="after")
    def require_both_coordinates(self) -> "LocationQuery":
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be provided together")
        return self


class NearbyLocation(BaseModel):
    id: str | int
    name: str
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    distance_km: float = Field(..., ge=0)
    type: str | None = None
    address: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocationTrackPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    speed: float | None = Field(default=0.0, ge=0)
    heading: float | None = Field(default=None, ge=0, lt=360)
    accuracy_m: float | None = Field(default=None, ge=0)


class LocationTrack(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    device_id: str | None = Field(default=None, max_length=120)
    points: list[LocationTrackPoint] = Field(default_factory=list)

    @property
    def latest(self) -> LocationTrackPoint | None:
        if not self.points:
            return None
        return max(self.points, key=lambda point: point.timestamp)
