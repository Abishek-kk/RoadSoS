from fastapi import APIRouter

from app.routes._data import load_json, with_distance, clean_phone_number


router = APIRouter(prefix="/towing", tags=["Towing Services"])


@router.get("")
async def list_towing(lat: float | None = None, lng: float | None = None):
    results = with_distance(load_json("towing.json"), lat, lng)
    for r in results:
        r["phone"] = clean_phone_number(r.get("phone"), "112")
    return results
