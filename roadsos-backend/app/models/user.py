# user.py — user schema
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class ContactBase(BaseModel):
    name: str
    phone: str
    relation: Optional[str] = None


class ContactCreate(ContactBase):
    pass


class ContactResponse(ContactBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    firebase_token: Optional[str] = None
    is_active: Optional[bool] = True
    is_admin: Optional[bool] = False


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    firebase_token: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    contacts: List[ContactResponse] = []

    class Config:
        from_attributes = True
