from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.routes.contacts import _contacts
from app.services.notification_service import notify_emergency_contacts


router = APIRouter(prefix="/sos", tags=["SOS"])


class SOSPayload(BaseModel):
    lat: float
    lng: float
    user: str | None = None
    user_id: int | None = None
    note: str | None = None


@router.post("")
async def trigger_sos(payload: SOSPayload):
    sos_id = f"sos-{int(datetime.now(timezone.utc).timestamp())}"
    user_name = (payload.user or "Abishek").strip()
    notification_results = notify_emergency_contacts(
        contacts=_contacts,
        user_name=user_name,
        lat=payload.lat,
        lng=payload.lng,
        note=payload.note,
    )
    submitted_count = sum(1 for result in notification_results if result.status in {"accepted", "queued", "sending", "sent", "submitted"})
    dry_run_count = sum(1 for result in notification_results if result.status == "dry_run")
    failed_count = sum(1 for result in notification_results if result.status == "failed")

    return {
        "ok": True,
        "sos_id": sos_id,
        "status": "active",
        "received": payload.model_dump(),
        "notifications": {
            "contacts": len(_contacts),
            "sent": submitted_count,
            "dry_run": dry_run_count,
            "failed": failed_count,
            "results": [result.__dict__ for result in notification_results],
        },
    }
