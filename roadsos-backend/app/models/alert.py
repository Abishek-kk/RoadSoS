# alert.py — alert schema
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class LocationDetails(BaseModel):
    lat: float
    lng: float
    address: str
    city: str
    state: str


class AlertBase(BaseModel):
    title: str
    type: str  # accident, weather, construction, breakdown, checkpoint, hazard, restriction, vip_movement, road_damage
    severity: str  # low, medium, high, critical
    status: str  # active, resolved, under_investigation
    description: str
    location: LocationDetails
    road: str
    direction: str
    lanes_blocked: int
    total_lanes: int
    vehicles_involved: int
    casualties: int
    injuries: int
    reported_at: datetime
    updated_at: datetime
    estimated_clearance: Optional[datetime] = None
    nearest_hospital_id: Optional[str] = None
    nearest_police_id: Optional[str] = None
    detour: Optional[str] = None
    source: str
    tags: List[str] = []


class AlertCreate(AlertBase):
    pass


class AlertResponse(AlertBase):
    id: str

    class Config:
        from_attributes = True
