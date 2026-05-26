from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter(prefix="/location", tags=["Location"])


class LocationPayload(BaseModel):
    lat: float
    lng: float
    speed: float | None = 0.0
    user_id: int | None = None


@router.post("")
async def post_location(payload: LocationPayload):
    return {"ok": True, "location": payload.model_dump()}
