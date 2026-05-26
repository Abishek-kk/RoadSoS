# sos.py — SOS event schema
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SOSBase(BaseModel):
    lat: float
    lng: float


class SOSCreate(SOSBase):
    user_id: Optional[int] = None


class SOSResponse(SOSBase):
    id: int
    user_id: Optional[int] = None
    status: str
    danger_zone_id: Optional[str] = None
    nearest_hospital_id: Optional[str] = None
    nearest_police_id: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True
