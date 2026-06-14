# notification_service.py - Firebase FCM + Twilio SMS/WhatsApp

import logging
from dataclasses import dataclass

from app.config import get_env_value

logger = logging.getLogger("roadsos.notifications")


@dataclass
class NotificationResult:
    contact_name: str
    phone: str
    channel: str
    status: str
    sid: str | None = None
    error: str | None = None


def build_sos_message(user_name: str, lat: float, lng: float, note: str | None = None) -> str:
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    detail = f" Note: {note}." if note else ""
    return (
        f"Emergency SOS: Your friend {user_name} is in an accident and needs help."
        f"{detail} Last known location: {maps_link}. Please respond immediately or contact 112/108."
    )


def notify_emergency_contacts(
    contacts: list[dict[str, str | None]],
    user_name: str,
    lat: float,
    lng: float,
    note: str | None = None,
) -> list[NotificationResult]:
    message = build_sos_message(user_name, lat, lng, note)
    results: list[NotificationResult] = []

    for contact in contacts:
        phone = normalize_phone_number(contact.get("phone") or "")
        name = contact.get("name") or "Emergency contact"
        if not phone:
            results.append(NotificationResult(name, phone, "whatsapp", "skipped", error="Missing phone number"))
            continue

        wants_sms = contact.get("notify_sms") is not False
        wants_whatsapp = contact.get("notify_whatsapp") is not False

        if wants_sms:
            results.append(send_sms(name, phone, message))
        else:
            results.append(NotificationResult(name, phone, "sms", "skipped", error="SMS notifications disabled"))

        if wants_whatsapp:
            results.append(send_whatsapp(name, phone, message))
        else:
            results.append(NotificationResult(name, phone, "whatsapp", "skipped", error="WhatsApp notifications disabled"))

    return results


def send_sms(contact_name: str, phone: str, message: str) -> NotificationResult:
    if not twilio_sms_configured():
        logger.info("SMS dry run to %s: %s", phone, message)
        return NotificationResult(contact_name, phone, "sms", "dry_run", error="TWILIO_PHONE_NUMBER is not configured")

    try:
        client = twilio_client()
        sent = client.messages.create(
            body=message,
            from_=normalize_phone_number(get_env_value("TWILIO_PHONE_NUMBER")),
            to=phone,
        )
        return NotificationResult(contact_name, phone, "sms", sent.status or "submitted", sid=sent.sid)
    except Exception as exc:
        logger.error("Failed to send SMS to %s", phone, exc_info=True)
        return NotificationResult(contact_name, phone, "sms", "failed", error=str(exc))


def send_whatsapp(contact_name: str, phone: str, message: str) -> NotificationResult:
    if not twilio_whatsapp_configured():
        logger.info("WhatsApp dry run to %s: %s", phone, message)
        return NotificationResult(contact_name, phone, "whatsapp", "dry_run")

    try:
        client = twilio_client()
        sent = client.messages.create(
            body=message,
            from_=format_whatsapp_number(get_env_value("TWILIO_WHATSAPP_NUMBER")),
            to=format_whatsapp_number(phone),
        )
        return NotificationResult(contact_name, phone, "whatsapp", sent.status or "submitted", sid=sent.sid)
    except Exception as exc:
        logger.error("Failed to send WhatsApp to %s", phone, exc_info=True)
        return NotificationResult(contact_name, phone, "whatsapp", "failed", error=str(exc))


def twilio_client():
    from twilio.rest import Client

    return Client(get_env_value("TWILIO_ACCOUNT_SID"), get_env_value("TWILIO_AUTH_TOKEN"))


def twilio_whatsapp_configured() -> bool:
    return bool(
        get_env_value("TWILIO_ACCOUNT_SID")
        and get_env_value("TWILIO_AUTH_TOKEN")
        and get_env_value("TWILIO_WHATSAPP_NUMBER")
    )


def twilio_sms_configured() -> bool:
    return bool(
        get_env_value("TWILIO_ACCOUNT_SID")
        and get_env_value("TWILIO_AUTH_TOKEN")
        and get_env_value("TWILIO_PHONE_NUMBER")
    )


def format_whatsapp_number(phone: str) -> str:
    normalized = phone.removeprefix("whatsapp:")
    return f"whatsapp:{normalize_phone_number(normalized)}"


def normalize_phone_number(phone: str) -> str:
    return "".join(phone.split())
