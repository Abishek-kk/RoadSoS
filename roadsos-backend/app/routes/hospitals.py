from fastapi import APIRouter

from app.routes._data import load_json, nearest_with_fallback, fetch_osm_amenities, clean_phone_number
from app.services.nearest_route_service import attach_route_waypoints


router = APIRouter(prefix="/hospitals", tags=["Hospitals"])


BAD_HOSPITAL_COORDINATE_ROWS = {
    "TN00868",
    "TN00885",
    "TN00918",
    "TN00922",
    "TN00940",
    "TN00989",
    "TN00998",
}


@router.get("")
async def list_hospitals(lat: float | None = None, lng: float | None = None):
    """List hospitals near a given `lat,lng`. Returns OSM results when available,
    otherwise falls back to bundled `hospitals.json` filtered to a 25 km radius.
    """
    if lat is not None and lng is not None:
        osm_results = await fetch_osm_amenities(lat, lng, "hospital")
        if osm_results:
            return attach_route_waypoints(osm_results, lat, lng)

    # Use a 25 km search radius and limit to 20 results by default
    rows = [
        row
        for row in load_json("hospitals.json")
        if row.get("id") not in BAD_HOSPITAL_COORDINATE_ROWS
    ]
    results = nearest_with_fallback(rows, lat, lng, max_km=25.0, limit=20, fallback_limit=10)
    for r in results:
        r["phone"] = clean_phone_number(r.get("phone"), "108")
        # Provide a tel: link and a directions URL for client use
        r["call_url"] = f"tel:{r['phone']}"
        if r.get("lat") is not None and r.get("lng") is not None:
            r["directions_url"] = f"https://www.google.com/maps/dir/?api=1&destination={r.get('lat')},{r.get('lng')}"
    return attach_route_waypoints(results, lat, lng)
