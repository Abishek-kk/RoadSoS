from fastapi import APIRouter

from app.routes._data import distance_km, load_json


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("")
async def list_alerts(lat: float | None = None, lng: float | None = None):
    alerts = []
    for item in load_json("road_alerts.json"):
        location = item["location"]
        distance = item.get("distance_km")
        if lat is not None and lng is not None:
            distance = distance_km(lat, lng, location["lat"], location["lng"])

        alerts.append(
            {
                **item,
                "message": item["description"],
                "lat": location["lat"],
                "lng": location["lng"],
                "created_at": item["reported_at"],
                "distance_km": distance,
            }
        )

    if lat is not None and lng is not None:
        alerts.sort(key=lambda row: row["distance_km"])
    return alerts
