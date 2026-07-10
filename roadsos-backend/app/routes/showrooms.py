from fastapi import APIRouter, Query

from app.services.nearest_route_service import attach_route_waypoints
from app.services.showroom_service import ShowroomService


router = APIRouter(prefix="/showrooms", tags=["Showrooms"])


@router.get("")
async def list_showrooms(
    lat: float | None = None,
    lng: float | None = None,
    city: str | None = None,
    district: str | None = None,
    pincode: str | None = None,
    limit: int = Query(20, ge=1, le=50),
):
    """List showrooms from the verified bundled showroom dataset."""
    service = ShowroomService()
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
