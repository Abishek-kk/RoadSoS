from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.location import LocationCreate, LocationLogResponse
from app.services import danger_zone_service, location_service
from db.database import get_db


router = APIRouter(prefix="/location", tags=["Location"])


@router.post("")
async def post_location(payload: LocationCreate, db: Session = Depends(get_db)):
    location_log = location_service.log_location(db, payload)

    danger_zones = danger_zone_service.load_danger_zones()
    alerts = danger_zone_service.active_geofence_alerts(
        payload.lat,
        payload.lng,
        danger_zones,
        warning_buffer_km=6.0,
    )
    risk = danger_zone_service.get_road_risk_assessment(
        lat=payload.lat,
        lng=payload.lng,
        speed=payload.speed,
        when=payload.recorded_at,
    )

    return {
        "ok": True,
        "location": LocationLogResponse.model_validate(location_log),
        "alerts": alerts,
        "risk": risk,
    }
