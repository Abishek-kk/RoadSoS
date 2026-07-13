from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.routes._data import distance_km, load_json
from db import crud
from db.database import get_db


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


@router.get("/recent")
async def recent_danger_zone_alerts(
    user_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    radius_km: float = Query(25.0, gt=0, le=500),
    db: Session = Depends(get_db),
):
    events = crud.get_recent_danger_zone_alerts(
        db,
        user_id,
        limit=limit,
        lat=lat,
        lng=lng,
        radius_km=radius_km if lat is not None and lng is not None else None,
    )
    return {
        "ok": True,
        "alerts": [
            {
                "id": e.id,
                "zone_id": e.zone_id,
                "zone_name": e.zone_name,
                "risk_level": e.risk_level,
                "risk_score": e.risk_score,
                "distance_km": e.distance_km,
                "inside_zone": e.inside_zone,
                "message": e.message,
                "advisory": e.advisory,
                "lat": e.lat,
                "lng": e.lng,
                "notified_push": e.notified_push,
                "notified_sms": e.notified_sms,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }
