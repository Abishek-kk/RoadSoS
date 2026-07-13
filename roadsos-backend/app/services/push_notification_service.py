import json
import logging
from typing import Any

from app.config import get_vapid_claims_email, get_vapid_private_key

logger = logging.getLogger("roadsos.push")


def send_danger_zone_push(subscription: Any, zone: dict) -> bool:
    private_key = get_vapid_private_key()
    claims_email = get_vapid_claims_email()
    if not private_key:
        logger.info("Push dry run for %s: VAPID_PRIVATE_KEY is not configured", zone.get("zone_id"))
        return False

    try:
        from pywebpush import WebPushException, webpush
    except Exception:
        logger.error("pywebpush is not installed; skipping push notification", exc_info=True)
        return False

    payload = {
        "title": "RoadSoS Danger Zone",
        "body": zone.get("message") or f"Approaching {zone.get('zone_name', 'a danger zone')}.",
        "zoneId": zone.get("zone_id"),
        "url": "/",
    }
    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh,
            "auth": subscription.auth,
        },
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims={"sub": f"mailto:{claims_email or 'admin@roadsos.app'}"},
        )
        return True
    except WebPushException as exc:
        logger.error("Failed to send push notification to %s", subscription.endpoint, exc_info=True)
        return False
    except Exception:
        logger.error("Unexpected push notification failure for %s", subscription.endpoint, exc_info=True)
        return False
