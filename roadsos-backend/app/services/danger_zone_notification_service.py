from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy.orm import Session

from app.config import get_danger_zone_sms_cooldown_minutes
from app.services import notification_service, push_notification_service
from db import crud, models

logger = logging.getLogger("roadsos.danger_zone_notifications")

PUSH_RISK_LEVELS = {"high", "very high", "critical"}
SMS_RISK_LEVELS = {"critical"}
_notified_until: dict[tuple[int, str, str], datetime] = {}


def notify_for_alerts(
    db: Session,
    user_id: int,
    alerts: list[dict],
    lat: float,
    lng: float,
) -> None:
    user = crud.get_user(db, user_id)
    if not user:
        return

    for alert in alerts:
        risk_level = str(alert.get("risk_level") or "").strip().lower()
        zone_id = str(alert.get("zone_id") or "")
        if not zone_id:
            continue

        notified_push = False
        notified_sms = False

        if risk_level in PUSH_RISK_LEVELS and _claim_cooldown(user_id, zone_id, "push", cooldown_minutes()):
            send_pushes(db, user_id, alert)
            notified_push = True

        if risk_level in SMS_RISK_LEVELS and has_real_phone(user) and _claim_cooldown(user_id, zone_id, "sms", cooldown_minutes()):
            try:
                notification_service.notify_user_of_danger_zone(user.phone, alert, lat, lng)
                notified_sms = True
            except Exception:
                logger.error("Danger-zone SMS/WhatsApp notification failed for zone %s", zone_id, exc_info=True)

        try:
            crud.log_danger_zone_alert_event(
                db,
                user_id,
                alert,
                lat,
                lng,
                notified_push=notified_push,
                notified_sms=notified_sms,
            )
        except Exception:
            logger.error("Danger-zone alert event persistence failed for zone %s", zone_id, exc_info=True)


def send_pushes(db: Session, user_id: int, alert: dict) -> None:
    for subscription in crud.get_push_subscriptions(db, user_id):
        try:
            push_notification_service.send_danger_zone_push(subscription, alert)
        except Exception:
            logger.error("Danger-zone push notification failed for subscription %s", subscription.id, exc_info=True)


def has_real_phone(user: models.User) -> bool:
    phone = (user.phone or "").strip()
    return bool(phone and phone != crud.DEFAULT_SYSTEM_USER_PHONE)


def cooldown_minutes() -> int:
    return get_danger_zone_sms_cooldown_minutes()


def _claim_cooldown(user_id: int, zone_id: str, channel: str, minutes: int) -> bool:
    now = datetime.now(UTC)
    key = (user_id, zone_id, channel)
    expires_at = _notified_until.get(key)
    if expires_at and expires_at > now:
        return False
    _notified_until[key] = now + timedelta(minutes=minutes)
    _prune_expired(now)
    return True


def _prune_expired(now: datetime) -> None:
    expired = [key for key, expires_at in _notified_until.items() if expires_at <= now]
    for key in expired:
        _notified_until.pop(key, None)


def clear_cooldowns() -> None:
    _notified_until.clear()
