from fastapi import APIRouter, Query

from app.services.hospital_service import HospitalService
from app.services.nearest_route_service import attach_route_waypoints


router = APIRouter(prefix="/hospitals", tags=["Hospitals"])


@router.get("")
async def list_hospitals(
    lat: float | None = None,
    lng: float | None = None,
    city: str | None = None,
    district: str | None = None,
    pincode: str | None = None,
    limit: int = Query(20, ge=1, le=50),
):
    """List hospitals from the verified bundled hospital dataset."""
    service = HospitalService()
    if pincode:
        return service.search_by_pincode(pincode, limit=limit)
    if district:
        return service.search_by_district(district, limit=limit)
    if city:
        return service.search_by_city(city, limit=limit)
    if lat is not None and lng is not None:
        results = service.find_nearest(lat, lng, limit=limit)
        return attach_route_waypoints(results, lat, lng)
    return [service.format_result(row) for row in service.load_database()[:limit]]
