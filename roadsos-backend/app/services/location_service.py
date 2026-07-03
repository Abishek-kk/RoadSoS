# location_service.py — GPS processing + Haversine
from sqlalchemy.orm import Session
from typing import List, Optional

from app.algorithms import haversine
from app.models.location import LocationCreate
from app.services.hospital_service import HospitalService
from app.services.police_service import PoliceService
from app.services.towing_service import TowingService
from db import crud, models


# Re-expose core GPS mathematical functions
Coordinate = haversine.Coordinate
haversine_distance_km = haversine.haversine_distance_km
haversine_distance_m = haversine.haversine_distance_m
distance_km = haversine.distance_km
distance_m = haversine.distance_m
bearing_degrees = haversine.bearing_degrees
compass_direction = haversine.compass_direction
destination_point = haversine.destination_point
midpoint = haversine.midpoint
bounding_box = haversine.bounding_box
with_distances = haversine.with_distances
nearest_point = haversine.nearest_point
points_within_radius = haversine.points_within_radius


def log_location(db: Session, payload: LocationCreate) -> models.LocationLog:
    """
    Persist the user's/device's GPS telemetry coordinate update to the database.
    """
    # Ensure system user exists if user_id is not specified
    if not payload.user_id:
        system_user = crud.get_or_create_system_user(db)
        payload.user_id = system_user.id

    return crud.create_location_log(db, payload)


def get_location_history(db: Session, user_id: int, limit: int = 50) -> List[models.LocationLog]:
    """
    Retrieve location history logs for a user, newest to oldest.
    """
    return crud.get_user_location_history(db, user_id, limit=limit)


def get_latest_location(db: Session, user_id: int) -> Optional[models.LocationLog]:
    """
    Get the most recent location log for a user.
    """
    return crud.get_latest_user_location(db, user_id)


def findNearestHospital(lat: float, lng: float, limit: int = 3) -> list[dict]:
    """Return top nearest hospitals from the verified local hospital dataset."""
    return HospitalService().find_nearest(lat, lng, limit=limit)


def findNearestPolice(lat: float, lng: float, limit: int = 3) -> list[dict]:
    """Return top nearest police stations from the verified local police dataset."""
    return PoliceService().find_nearest(lat, lng, limit=limit)


def findNearestTow(lat: float, lng: float, limit: int = 3) -> list[dict]:
    """Return top nearest towing services from the verified local towing dataset."""
    return TowingService().find_nearest(lat, lng, limit=limit)


def find_nearest_hospital(lat: float, lng: float, limit: int = 3) -> list[dict]:
    return findNearestHospital(lat, lng, limit=limit)


def find_nearest_police(lat: float, lng: float, limit: int = 3) -> list[dict]:
    return findNearestPolice(lat, lng, limit=limit)


def find_nearest_tow(lat: float, lng: float, limit: int = 3) -> list[dict]:
    return findNearestTow(lat, lng, limit=limit)
