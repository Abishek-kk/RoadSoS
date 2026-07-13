from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_danger_zone_alert_radius_km
from app.models.location import LocationCreate, LocationLogResponse
from app.services import danger_zone_notification_service, danger_zone_service, location_service
from app.services.route_service import get_route_between_points
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
        max_total_radius_km=get_danger_zone_alert_radius_km(),
    )
    danger_zone_notification_service.notify_for_alerts(
        db,
        location_log.user_id,
        alerts,
        payload.lat,
        payload.lng,
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


@router.get("/nearest-hospital")
async def nearest_hospital(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    limit: int = Query(3, ge=1, le=10),
) -> dict[str, Any]:
    return {
        "ok": True,
        "results": location_service.findNearestHospital(lat, lng, limit=limit),
    }


@router.get("/nearest-police")
async def nearest_police(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    limit: int = Query(3, ge=1, le=10),
) -> dict[str, Any]:
    return {
        "ok": True,
        "results": location_service.findNearestPolice(lat, lng, limit=limit),
    }


@router.get("/nearest-tow")
async def nearest_tow(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    limit: int = Query(3, ge=1, le=10),
) -> dict[str, Any]:
    return {
        "ok": True,
        "results": location_service.findNearestTow(lat, lng, limit=limit),
    }


@router.get("/danger-zones")
async def nearby_danger_zones(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(5.0, gt=0, le=50),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return {
        "ok": True,
        "radius_km": radius_km,
        "results": danger_zone_service.get_nearby_danger_roads(
            lat,
            lng,
            radius_km=radius_km,
            limit=limit,
        ),
    }


@router.get("/route")
async def route_to_service(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    service: str = Query("hospital", description="hospital, police, tow, or towing"),
    to_lat: float | None = Query(None, ge=-90, le=90),
    to_lng: float | None = Query(None, ge=-180, le=180),
) -> dict[str, Any]:
    destination = None
    normalized_service = service.strip().lower()

    if to_lat is not None and to_lng is not None:
        destination = {
            "id": "custom_destination",
            "name": "Selected destination",
            "category": normalized_service,
            "lat": to_lat,
            "lng": to_lng,
        }
    elif normalized_service == "police":
        destination = first_result(location_service.findNearestPolice(lat, lng, limit=1))
    elif normalized_service in {"tow", "towing", "towing_service"}:
        destination = first_result(location_service.findNearestTow(lat, lng, limit=1))
    else:
        destination = first_result(location_service.findNearestHospital(lat, lng, limit=1))
        normalized_service = "hospital"

    if not destination or destination.get("lat") is None or destination.get("lng") is None:
        return {
            "ok": False,
            "service": normalized_service,
            "destination": destination,
            "route": None,
            "message": "No verified routable destination found in local data.",
        }

    route = get_route_between_points(
        lat,
        lng,
        float(destination["lat"]),
        float(destination["lng"]),
        destination_id=str(destination.get("id") or "destination"),
        destination_name=str(destination.get("name") or "Destination"),
    )
    return {
        "ok": True,
        "service": normalized_service,
        "destination": destination,
        "route": route,
    }


def first_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    return results[0] if results else None
