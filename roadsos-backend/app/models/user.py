"""
user.py - user and emergency-contact schemas.

These models support RoadSoS account profiles, Firebase device tokens, and the
emergency contacts used by SOS notifications.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactRelation(StrEnum):
    FAMILY = "Family"
    FRIEND = "Friend"
    SPOUSE = "Spouse"
    PARENT = "Parent"
    SIBLING = "Sibling"
    DOCTOR = "Doctor"
    OTHER = "Other"


class UserRole(StrEnum):
    USER = "user"
    RESPONDER = "responder"
    ADMIN = "admin"


class ContactBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=7, max_length=20)
    relation: ContactRelation | str | None = None
    is_primary: bool = False
    priority: int = Field(default=1, ge=1, le=10)
    notify_sms: bool = True
    notify_whatsapp: bool = True
    notify_call: bool = False

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        if not PHONE_RE.match(normalized):
            raise ValueError("phone must contain 7 to 15 digits, optionally prefixed with +")
        return normalized

    @field_validator("relation", mode="before")
    @classmethod
    def normalize_relation(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ContactCreate(ContactBase):
    user_id: int | None = Field(default=None, ge=1)


class ContactUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    relation: ContactRelation | str | None = None
    is_primary: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10)
    notify_sms: bool | None = None
    notify_whatsapp: bool | None = None
    notify_call: bool | None = None

    @field_validator("phone")
    @classmethod
    def validate_optional_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ContactBase.validate_phone(value)


class ContactResponse(ContactBase):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, use_enum_values=True)

    id: int | str
    user_id: int | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None


class UserPreferences(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    language: str = Field(default="en", min_length=2, max_length=10)
    emergency_call_enabled: bool = True
    share_location_with_contacts: bool = True
    alert_radius_km: float = Field(default=10.0, gt=0, le=200)
    push_notifications_enabled: bool = True
    whatsapp_notifications_enabled: bool = True


class UserBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=7, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    firebase_token: str | None = Field(default=None, max_length=4096)
    role: UserRole = UserRole.USER
    is_active: bool = True
    is_admin: bool = False
    preferences: UserPreferences = Field(default_factory=UserPreferences)

    @field_validator("phone")
    @classmethod
    def validate_user_phone(cls, value: str) -> str:
        return ContactBase.validate_phone(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not EMAIL_RE.match(normalized):
            raise ValueError("email must be a valid email address")
        return normalized

    @field_validator("firebase_token", mode="before")
    @classmethod
    def empty_token_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def sync_admin_role(self) -> "UserBase":
        if self.role == UserRole.ADMIN:
            self.is_admin = True
        elif self.is_admin:
            self.role = UserRole.ADMIN
        return self


class UserCreate(UserBase):
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    firebase_token: str | None = Field(default=None, max_length=4096)
    role: UserRole | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    preferences: UserPreferences | None = None

    @field_validator("phone")
    @classmethod
    def validate_optional_user_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ContactBase.validate_phone(value)

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        return UserBase.validate_email(value)

    @field_validator("firebase_token", mode="before")
    @classmethod
    def empty_update_token_to_none(cls, value: Any) -> Any:
        return UserBase.empty_token_to_none(value)


class UserLogin(BaseModel):
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    firebase_token: str | None = Field(default=None, max_length=4096)

    @field_validator("phone")
    @classmethod
    def validate_login_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ContactBase.validate_phone(value)

    @field_validator("email")
    @classmethod
    def validate_login_email(cls, value: str | None) -> str | None:
        return UserBase.validate_email(value)

    @model_validator(mode="after")
    def require_identifier(self) -> "UserLogin":
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        return self


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, use_enum_values=True)

    id: int
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_location_lat: float | None = Field(default=None, ge=-90, le=90)
    last_location_lng: float | None = Field(default=None, ge=-180, le=180)
    last_seen_at: datetime | None = None
    contacts: list[ContactResponse] = Field(default_factory=list)


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, use_enum_values=True)

    id: int
    name: str
    phone: str
    role: UserRole | str = UserRole.USER
    is_active: bool = True
    contact_count: int = 0


class UserListResponse(BaseModel):
    users: list[UserResponse] = Field(default_factory=list)
    count: int | None = None

    @model_validator(mode="after")
    def fill_count(self) -> "UserListResponse":
        if self.count is None:
            self.count = len(self.users)
        return self


def normalize_phone(phone: str) -> str:
    """Normalize common phone formatting while preserving a leading +."""
    text = str(phone).strip()
    prefix = "+" if text.startswith("+") else ""
    digits = "".join(ch for ch in text if ch.isdigit())
    return f"{prefix}{digits}"
