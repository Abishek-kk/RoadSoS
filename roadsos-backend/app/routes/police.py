from fastapi import APIRouter

from app.routes._data import load_json, with_distance, fetch_osm_amenities, clean_phone_number


router = APIRouter(prefix="/police", tags=["Police"])


@router.get("")
async def list_police(lat: float | None = None, lng: float | None = None):
    if lat is not None and lng is not None:
        osm_results = await fetch_osm_amenities(lat, lng, "police")
        if osm_results:
            return osm_results
            
    results = with_distance(load_json("police_stations.json"), lat, lng)
    for r in results:
        r["phone"] = clean_phone_number(r.get("phone"), "100")
    return results

