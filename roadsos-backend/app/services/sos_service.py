# sos_service.py — SOS workflow + notifications
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session

from app.models.sos import SOSCreate
from app.services.notification_service import notify_emergency_contacts, NotificationResult
from db import crud


def _notification_summary(results: list[NotificationResult]) -> dict[str, int | list[dict[str, Any]]]:
    sent_statuses = {"accepted", "queued", "sending", "sent", "submitted"}
    contact_count = len({(result.contact_name, result.phone) for result in results})
    sent = sum(1 for result in results if str(result.status) in sent_statuses)
    dry_run = sum(1 for result in results if str(result.status) == "dry_run")
    failed = sum(1 for result in results if str(result.status) == "failed")
    skipped = sum(1 for result in results if str(result.status) == "skipped")
    return {
        "contacts": contact_count,
        "attempts": len(results),
        "sent": sent,
        "dry_run": dry_run,
        "failed": failed,
        "skipped": skipped,
        "results": [result.__dict__ for result in results],
    }


def trigger_sos_workflow(db: Session, payload: SOSCreate) -> dict[str, Any]:
    """
    Handles the complete SOS event lifecycle:
    1. Resolves the user (or uses the shared system user).
    2. Fetches user's emergency contacts.
    3. Triggers WhatsApp/Twilio notifications.
    4. Records the active SOS event in the database.
    5. Returns a detailed status report including notification statistics.
    """
    sos_id = f"sos-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    user_name = (payload.user or "Abishek").strip()

    if payload.user_id:
        contacts = crud.get_emergency_contacts(db, payload.user_id)
    else:
        system_user = crud.get_or_create_system_user(db)
        contacts = crud.get_emergency_contacts(db, system_user.id)

    contact_list = [
        {
            "name": contact.name,
            "phone": contact.phone,
            "relation": contact.relation,
            "notify_whatsapp": contact.notify_whatsapp,
        }
        for contact in contacts
    ]

    results = notify_emergency_contacts(contact_list, user_name, payload.lat, payload.lng, payload.note)
    crud.create_sos_event(db, payload)

    return {
        "ok": True,
        "sos_id": sos_id,
        "status": "active",
        "received": payload.model_dump(),
        "maps_url": payload.maps_url,
        "emergency_numbers": ["112", "108"],
        "message": "SOS recorded and WhatsApp notifications were sent to your saved contacts.",
        "notifications": _notification_summary(results),
    }
