from __future__ import annotations

import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.structured_service import (
    estimate_eta_minutes,
    format_eta,
    parse_float,
)
from db import models
from db.database import SessionLocal


logger = logging.getLogger("roadsos.ambulances")
DEFAULT_AMBULANCE_UPDATE_SECONDS = 20
AMBULANCE_SPEED_KMPH = 45.0
EMERGENCY_AMBULANCE_PHONE = "108"
MIN_MOCK_DISTANCE_KM = 3.0
MAX_MOCK_DISTANCE_KM = 8.0

SEED_AMBULANCES = [
    ("AMB001", "7305647064"),
    ("AMB002", "9843947069"),
    ("AMB003", "9176271135"),
]


def seed_ambulances(db: Session) -> None:
    seeded_ids = {ambulance_id for ambulance_id, _phone in SEED_AMBULANCES}
    busy_id = random.choice(tuple(seeded_ids))
    existing = {
        ambulance.ambulance_id: ambulance
        for ambulance in db.query(models.Ambulance).all()
    }
    for ambulance in existing.values():
        if ambulance.ambulance_id not in seeded_ids:
            db.delete(ambulance)

    now = datetime.now(timezone.utc)
    for ambulance_id, phone in SEED_AMBULANCES:
        ambulance = existing.get(ambulance_id)
        if ambulance is None:
            ambulance = models.Ambulance(ambulance_id=ambulance_id)
            db.add(ambulance)
        ambulance.phone = phone
        ambulance.lat = None
        ambulance.lng = None
        ambulance.status = "busy" if ambulance_id == busy_id else "available"
        ambulance.distance_km = random_distance_km()
        ambulance.updated_at = now
    db.commit()


def find_nearest(db: Session, lat: float, lng: float, limit: int = 3) -> list[dict[str, Any]]:
    service = AmbulanceService(db)
    return service.find_nearest(lat, lng, limit=limit)


class AmbulanceService:
    category = "ambulance"
    average_speed_kmph = AMBULANCE_SPEED_KMPH

    def __init__(self, db: Session) -> None:
        self.db = db

    def find_nearest(self, lat: float, lng: float, limit: int = 3) -> list[dict[str, Any]]:
        refresh_mock_fleet(self.db)
        ambulances = sorted(
            self.db.query(models.Ambulance).all(),
            key=lambda ambulance: (
                status_rank(ambulance.status),
                ambulance.distance_km if ambulance.distance_km is not None else float("inf"),
                ambulance.ambulance_id,
            ),
        )
        return [self.format_result(ambulance) for ambulance in ambulances]

    def format_result(self, ambulance: models.Ambulance, distance: float | None = None) -> dict[str, Any]:
        lat = parse_float(ambulance.lat)
        lng = parse_float(ambulance.lng)
        distance_km = round(float(distance), 1) if distance is not None else parse_float(ambulance.distance_km)
        eta_minutes = estimate_eta_minutes(distance_km, self.average_speed_kmph)
        status = normalize_status(ambulance.status)
        phone = str(ambulance.phone or EMERGENCY_AMBULANCE_PHONE)
        result: dict[str, Any] = {
            "id": ambulance.ambulance_id,
            "ambulance_id": ambulance.ambulance_id,
            "name": f"Ambulance {ambulance.ambulance_id}",
            "category": self.category,
            "type": "Ambulance",
            "address": "Mock ambulance fleet",
            "lat": lat,
            "lng": lng,
            "gps": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
            "phone": phone,
            "emergency_phone": EMERGENCY_AMBULANCE_PHONE,
            "distance_km": distance_km,
            "eta_minutes": eta_minutes,
            "eta": format_eta(eta_minutes),
            "status": status,
            "availability": status.title(),
            "call_url": f"tel:{phone}",
            "updated_at": ambulance.updated_at.isoformat() if ambulance.updated_at else None,
        }
        if lat is not None and lng is not None:
            result["directions_url"] = f"https://www.openstreetmap.org/directions?to={lat}%2C{lng}"
        return result


def status_rank(value: str | None) -> int:
    return 0 if normalize_status(value) == "available" else 1


def normalize_status(value: str | None) -> str:
    return "busy" if str(value or "").lower() == "busy" else "available"


def refresh_mock_fleet(db: Session) -> None:
    seed_ambulances(db)
    ambulances = db.query(models.Ambulance).all()
    if not ambulances:
        return
    busy_id = random.choice([ambulance.ambulance_id for ambulance in ambulances])
    now = datetime.now(timezone.utc)
    for ambulance in ambulances:
        ambulance.status = "busy" if ambulance.ambulance_id == busy_id else "available"
        ambulance.distance_km = random_distance_km()
        ambulance.lat = None
        ambulance.lng = None
        ambulance.updated_at = now
    db.commit()


async def run_ambulance_simulator(stop_event: asyncio.Event | None = None) -> None:
    interval = ambulance_update_interval_seconds()
    logger.info("Ambulance simulator started with %ss interval.", interval)
    while stop_event is None or not stop_event.is_set():
        update_ambulance_positions()
        try:
            if stop_event is None:
                await asyncio.sleep(interval)
            else:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
    logger.info("Ambulance simulator stopped.")


def update_ambulance_positions() -> None:
    db = SessionLocal()
    try:
        refresh_mock_fleet(db)
    except Exception:
        logger.exception("Ambulance simulator update failed.")
        db.rollback()
    finally:
        db.close()


def ambulance_update_interval_seconds() -> int:
    raw_value = os.getenv("AMBULANCE_UPDATE_INTERVAL_SECONDS")
    try:
        return max(5, int(raw_value)) if raw_value else DEFAULT_AMBULANCE_UPDATE_SECONDS
    except ValueError:
        return DEFAULT_AMBULANCE_UPDATE_SECONDS


def random_distance_km() -> float:
    return round(random.uniform(MIN_MOCK_DISTANCE_KM, MAX_MOCK_DISTANCE_KM), 1)
