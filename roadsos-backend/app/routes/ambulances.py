from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.dependencies import DbSession
from app.services import ambulance_service
from app.services.nearest_route_service import attach_route_waypoints


router = APIRouter(prefix="/ambulances", tags=["Ambulances"])


@router.get("")
async def list_ambulances(
    lat: float,
    lng: float,
    limit: int = Query(3, ge=1, le=50),
    db: Session = DbSession,
):
    """List nearest live ambulances from the mutable ambulance table."""
    results = ambulance_service.find_nearest(db, lat, lng, limit=limit)
    return attach_route_waypoints(results, lat, lng)
