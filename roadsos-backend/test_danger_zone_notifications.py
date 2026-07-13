from fastapi.testclient import TestClient

from app.algorithms.geofencing import active_geofence_alerts
from app.main import app
from app.routes._data import cache_clear, load_json
from app.services import danger_zone_notification_service
from db import crud, models
from db.database import SessionLocal, init_db


def point_north(lat: float, km: float) -> float:
    return lat + (km / 111.195)


def test_alert_radius_uses_exact_total_cutoff():
    zone = {
        "id": "zone-1",
        "name": "Test Zone",
        "lat": 10.0,
        "lng": 77.0,
        "radius_km": 2.0,
        "risk_level": "high",
    }

    at_49 = active_geofence_alerts(point_north(10.0, 4.9), 77.0, [zone], max_total_radius_km=5.0)
    at_51 = active_geofence_alerts(point_north(10.0, 5.1), 77.0, [zone], max_total_radius_km=5.0)

    assert len(at_49) == 1
    assert at_49[0]["status"] == "nearby"
    assert at_51 == []


def test_madurai_point_records_do_not_create_broad_inside_zones():
    cache_clear()
    zones = load_json("danger_zones.json")
    alerts = active_geofence_alerts(9.9261, 78.1141, zones, max_total_radius_km=8.0)
    simmakkal = next(
        alert
        for alert in alerts
        if alert["district"] == "Madurai" and "Simmakkal" in alert["zone_name"]
    )

    assert simmakkal["status"] == "nearby"
    assert simmakkal["inside_zone"] is False
    assert simmakkal["distance_km"] > 0.25


def test_location_notifications_are_cooled_down(monkeypatch):
    danger_zone_notification_service.clear_cooldowns()
    zone = {
        "id": "zone-critical",
        "name": "Critical Curve",
        "lat": 10.0,
        "lng": 77.0,
        "radius_km": 2.0,
        "risk_level": "critical",
        "risk_score": 95,
        "advisory": "Slow down.",
    }
    calls = {"push": 0, "sms": 0}

    monkeypatch.setattr("app.services.danger_zone_service.load_danger_zones", lambda: [zone])
    monkeypatch.setattr("app.services.danger_zone_service.get_road_risk_assessment", lambda **kwargs: {})
    monkeypatch.setattr(
        "app.services.danger_zone_notification_service.send_pushes",
        lambda db, user_id, alert: calls.__setitem__("push", calls["push"] + 1),
    )
    monkeypatch.setattr(
        "app.services.notification_service.notify_user_of_danger_zone",
        lambda phone, zone, lat, lng: calls.__setitem__("sms", calls["sms"] + 1),
    )
    monkeypatch.setattr(
        "app.services.danger_zone_notification_service.has_real_phone",
        lambda user: True,
    )

    with TestClient(app) as client:
        first = client.post("/api/location", json={"lat": 10.0, "lng": 77.0})
        second = client.post("/api/location", json={"lat": 10.0, "lng": 77.0})

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == {"push": 1, "sms": 1}


def test_push_subscription_persists_and_location_calls_push_service(monkeypatch):
    danger_zone_notification_service.clear_cooldowns()
    zone = {
        "id": "zone-high",
        "name": "High Risk Junction",
        "lat": 10.0,
        "lng": 77.0,
        "radius_km": 2.0,
        "risk_level": "high",
        "risk_score": 80,
    }
    calls = {"push": 0}

    monkeypatch.setattr("app.services.danger_zone_service.load_danger_zones", lambda: [zone])
    monkeypatch.setattr("app.services.danger_zone_service.get_road_risk_assessment", lambda **kwargs: {})
    monkeypatch.setattr(
        "app.services.push_notification_service.send_danger_zone_push",
        lambda subscription, zone: calls.__setitem__("push", calls["push"] + 1) or True,
    )

    with TestClient(app) as client:
        subscribed = client.post(
            "/api/push/subscribe",
            json={"endpoint": "https://example.test/push/1", "keys": {"p256dh": "key", "auth": "auth"}},
        )
        located = client.post("/api/location", json={"lat": 10.0, "lng": 77.0})

    assert subscribed.status_code == 200
    assert subscribed.json()["ok"] is True
    assert located.status_code == 200
    assert calls["push"] >= 1


def test_log_danger_zone_alert_event_persists_and_dedupes(monkeypatch):
    init_db()
    monkeypatch.setenv("DANGER_ZONE_SMS_COOLDOWN_MINUTES", "45")
    zone_id = "zone-dedupe-test"
    alert = {
        "zone_id": zone_id,
        "zone_name": "Dedupe Test Zone",
        "risk_level": "high",
        "risk_score": 82,
        "distance_km": 1.2,
        "inside_zone": False,
        "message": "Approaching a high risk zone.",
        "advisory": "Slow down.",
    }

    db = SessionLocal()
    try:
        user = crud.get_or_create_system_user(db)
        db.query(models.DangerZoneAlertEvent).filter(
            models.DangerZoneAlertEvent.user_id == user.id,
            models.DangerZoneAlertEvent.zone_id == zone_id,
        ).delete()
        db.commit()

        first = crud.log_danger_zone_alert_event(
            db,
            user.id,
            alert,
            10.0,
            77.0,
            notified_push=True,
            notified_sms=False,
        )
        second = crud.log_danger_zone_alert_event(db, user.id, alert, 10.0, 77.0)
        count = db.query(models.DangerZoneAlertEvent).filter(
            models.DangerZoneAlertEvent.user_id == user.id,
            models.DangerZoneAlertEvent.zone_id == zone_id,
        ).count()
    finally:
        db.close()

    assert first.id == second.id
    assert first.zone_name == "Dedupe Test Zone"
    assert first.notified_push is True
    assert count == 1


def test_missing_notification_credentials_do_not_change_location_response(monkeypatch):
    danger_zone_notification_service.clear_cooldowns()
    zone = {
        "id": "zone-high-no-creds",
        "name": "No Creds Junction",
        "lat": 10.0,
        "lng": 77.0,
        "radius_km": 2.0,
        "risk_level": "high",
        "risk_score": 80,
    }

    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("app.services.danger_zone_service.load_danger_zones", lambda: [zone])
    monkeypatch.setattr("app.services.danger_zone_service.get_road_risk_assessment", lambda **kwargs: {})

    with TestClient(app) as client:
        response = client.post("/api/location", json={"lat": 10.0, "lng": 77.0})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["alerts"][0]["zone_id"] == "zone-high-no-creds"


def test_nearby_danger_zones_route_returns_district_road_records(monkeypatch):
    monkeypatch.setattr(
        "app.services.danger_zone_service.load_danger_zones",
        lambda: [
            {
                "id": "TVR0101",
                "road_name": "Nagapattinam - Gudalur Highway (NH-83) - Tiruvarur Town Approach",
                "name": "Nagapattinam - Gudalur Highway (NH-83) - Tiruvarur Town Approach - Tiruvarur Urban Outskirts",
                "city": "Tiruvarur Urban Outskirts",
                "district": "Tiruvarur",
                "lat": 10.7725,
                "lng": 79.6361,
                "radius_km": 2.0,
                "risk_level": "high",
                "risk_score": 7.5,
                "danger_type": [
                    "Heavy Pedestrian Congestion near Temple Entrance",
                    "Narrow Carriage Lanes with Encroachments",
                ],
                "recommended_speed": 25,
                "safety_tips": ["Reduce speed drastically when approaching the active market zones."],
            },
            {
                "id": "far-away",
                "name": "Far Away Zone",
                "lat": 11.5,
                "lng": 79.6,
                "radius_km": 2.0,
                "risk_level": "critical",
            },
        ],
    )

    with TestClient(app) as client:
        response = client.get("/api/location/danger-zones?lat=10.7725&lng=79.6361&radius_km=5")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert len(body["results"]) == 1
    assert body["results"][0]["zone_id"] == "TVR0101"
    assert body["results"][0]["road_name"].startswith("Nagapattinam - Gudalur Highway")
    assert body["results"][0]["recommended_speed"] == 25
