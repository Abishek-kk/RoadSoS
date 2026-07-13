# sos_service.py — SOS workflow + notifications
import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session

from app.models.sos import SOSCreate
from app.services import ambulance_service
from app.services import location_service
from app.services.notification_service import notify_emergency_contacts, NotificationResult
from app.services.route_service import get_route_between_points
from db import crud


logger = logging.getLogger("roadsos.sos")


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
    emergency_context = build_emergency_context(db, payload)

    return {
        "ok": True,
        "sos_id": sos_id,
        "status": "active",
        "received": payload.model_dump(),
        "maps_url": payload.maps_url,
        "emergency_numbers": ["112", "108"],
        "message": "SOS recorded and WhatsApp notifications were sent to your saved contacts.",
        "notifications": _notification_summary(results),
        "emergency_context": emergency_context,
    }


def build_emergency_context(db: Session, payload: SOSCreate) -> dict[str, Any]:
    nearest_ambulance = safe_first_result("ambulance", ambulance_service.find_nearest, db, payload.lat, payload.lng)
    nearest_hospital = safe_first_result("hospital", location_service.findNearestHospital, payload.lat, payload.lng)
    nearest_police = safe_first_result("police", location_service.findNearestPolice, payload.lat, payload.lng)
    nearest_tow = safe_first_result("towing", location_service.findNearestTow, payload.lat, payload.lng)

    route = None
    if nearest_hospital and nearest_hospital.get("lat") is not None and nearest_hospital.get("lng") is not None:
        try:
            route = get_route_between_points(
                payload.lat,
                payload.lng,
                float(nearest_hospital["lat"]),
                float(nearest_hospital["lng"]),
                destination_id=str(nearest_hospital.get("id") or "nearest_hospital"),
                destination_name=str(nearest_hospital.get("name") or "Nearest hospital"),
            )
        except Exception as exc:
            logger.warning("SOS route enrichment failed; returning service data without route. Error: %s", exc)

    return {
        "user_location": {"lat": payload.lat, "lng": payload.lng},
        "nearest_ambulance": nearest_ambulance,
        "nearest_hospital": nearest_hospital,
        "nearest_police": nearest_police,
        "nearest_tow": nearest_tow,
        "route": route,
    }


def first_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    return results[0] if results else None


def safe_first_result(label: str, finder, *args) -> dict[str, Any] | None:
    try:
        return first_result(finder(*args, limit=1))
    except Exception as exc:
        logger.warning("SOS %s lookup failed. Error: %s", label, exc)
        return None
