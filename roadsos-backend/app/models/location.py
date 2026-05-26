# location.py — GPS payload schema
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class LocationBase(BaseModel):
    lat: float
    lng: float
    speed: Optional[float] = 0.0


class LocationCreate(LocationBase):
    user_id: int


class LocationLogResponse(LocationBase):
    id: int
    user_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
