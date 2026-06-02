from typing import Any

from fastapi import APIRouter, Query

from app.ai.risk_scorer import assess_road_risk


router = APIRouter(prefix="/risk", tags=["Risk"])


@router.get("")
async def get_risk(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    return assess_road_risk(lat, lng)
