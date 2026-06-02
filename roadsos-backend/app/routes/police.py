from fastapi import APIRouter

from app.routes._data import load_json, nearest_with_fallback, fetch_osm_amenities, clean_phone_number
from app.services.nearest_route_service import attach_route_waypoints


router = APIRouter(prefix="/police", tags=["Police"])


@router.get("")
async def list_police(lat: float | None = None, lng: float | None = None):
    """List police stations near a given `lat,lng`. Try OSM first, otherwise use
    the bundled `police_stations.json` and filter to 25 km radius.
    """
    if lat is not None and lng is not None:
        osm_results = await fetch_osm_amenities(lat, lng, "police")
        if osm_results:
            return attach_route_waypoints(osm_results, lat, lng)

    results = nearest_with_fallback(load_json("police_stations.json"), lat, lng, max_km=25.0, limit=20, fallback_limit=10)
    for r in results:
        r["phone"] = clean_phone_number(r.get("phone"), "100")
        # Emergency call note and tel link for immediate response
        r["emergency_phone"] = r.get("emergency_phone") or "100"
        r["emergency_call"] = f"tel:{r['emergency_phone']}"
        r["emergency_note"] = "Dial 100 for immediate response."
        # Provide a tel: link and a directions URL for client use
        r["call_url"] = f"tel:{r['phone']}"
        if r.get("lat") is not None and r.get("lng") is not None:
            r["directions_url"] = f"https://www.google.com/maps/dir/?api=1&destination={r.get('lat')},{r.get('lng')}"
    return attach_route_waypoints(results, lat, lng)
