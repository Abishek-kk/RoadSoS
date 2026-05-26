from fastapi import APIRouter

from app.routes._data import load_json, nearest_with_fallback, clean_phone_number, fetch_overpass_towing


router = APIRouter(prefix="/towing", tags=["Towing Services"])


@router.get("")
async def list_towing(lat: float | None = None, lng: float | None = None):
    """List towing services near a given `lat,lng`. Try Overpass API first,
    otherwise fall back to bundled `towing.json` filtered to a 50 km radius."""
    if lat is not None and lng is not None:
        osm_results = await fetch_overpass_towing(lat, lng)
        if osm_results:
            return osm_results

    results = nearest_with_fallback(load_json("towing.json"), lat, lng, max_km=50.0, limit=20, fallback_limit=10)
    for r in results:
        r["phone"] = clean_phone_number(r.get("phone"), "112")
        # Provide a tel: link and a directions URL for client use
        r["call_url"] = f"tel:{r['phone']}"
        if r.get("lat") is not None and r.get("lng") is not None:
            r["directions_url"] = f"https://www.google.com/maps/dir/?api=1&destination={r.get('lat')},{r.get('lng')}"
    return results
