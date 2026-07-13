from __future__ import annotations

import asyncio
import logging
import math
import os
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.algorithms.haversine import distance_km
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
AMBULANCE_PHONE = "108"

SEED_AMBULANCES = [
    ("AMB001", 13.0506113, 80.0986529),
    ("AMB002", 13.043097, 80.2452985),
    ("AMB003", 12.9823769, 80.1938473),
    ("AMB004", 13.048103, 80.245059),
    ("AMB005", 13.1137635, 80.2861987),
]


def seed_ambulances(db: Session) -> None:
    if db.query(models.Ambulance).first():
        return
    for ambulance_id, lat, lng in SEED_AMBULANCES:
        db.add(
            models.Ambulance(
                ambulance_id=ambulance_id,
                lat=lat,
                lng=lng,
                status="available",
            )
        )
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
        ranked: list[tuple[models.Ambulance, float]] = []
        for ambulance in self.db.query(models.Ambulance).all():
            ambulance_lat = parse_float(ambulance.lat)
            ambulance_lng = parse_float(ambulance.lng)
            if ambulance_lat is None or ambulance_lng is None:
                continue
            ranked.append((ambulance, distance_km(lat, lng, ambulance_lat, ambulance_lng)))

        ranked.sort(
            key=lambda item: (
                status_rank(item[0].status),
                float(item[1]) if item[1] is not None else math.inf,
                item[0].ambulance_id,
            )
        )
        return [self.format_result(ambulance, distance) for ambulance, distance in ranked[:limit]]

    def format_result(self, ambulance: models.Ambulance, distance: float | None = None) -> dict[str, Any]:
        lat = parse_float(ambulance.lat)
        lng = parse_float(ambulance.lng)
        eta_minutes = estimate_eta_minutes(distance, self.average_speed_kmph)
        status = normalize_status(ambulance.status)
        result: dict[str, Any] = {
            "id": ambulance.ambulance_id,
            "ambulance_id": ambulance.ambulance_id,
            "name": f"Ambulance {ambulance.ambulance_id}",
            "category": self.category,
            "type": "Ambulance",
            "address": "Live GPS location",
            "lat": lat,
            "lng": lng,
            "gps": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
            "phone": AMBULANCE_PHONE,
            "emergency_phone": AMBULANCE_PHONE,
            "distance_km": distance,
            "eta_minutes": eta_minutes,
            "eta": format_eta(eta_minutes),
            "status": status,
            "availability": status.title(),
            "call_url": f"tel:{AMBULANCE_PHONE}",
            "updated_at": ambulance.updated_at.isoformat() if ambulance.updated_at else None,
        }
        if lat is not None and lng is not None:
            result["directions_url"] = f"https://www.openstreetmap.org/directions?to={lat}%2C{lng}"
        return result


def status_rank(value: str | None) -> int:
    return 0 if normalize_status(value) == "available" else 1


def normalize_status(value: str | None) -> str:
    return "busy" if str(value or "").lower() == "busy" else "available"


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
        seed_ambulances(db)
        for ambulance in db.query(models.Ambulance).all():
            if ambulance.lat is None or ambulance.lng is None:
                continue
            # Small jitter keeps the asset moving without jumping implausibly far in dev.
            ambulance.lat = clamp(float(ambulance.lat) + random.uniform(-0.0015, 0.0015), -90.0, 90.0)
            ambulance.lng = clamp(float(ambulance.lng) + random.uniform(-0.0015, 0.0015), -180.0, 180.0)
            if random.random() < 0.12:
                ambulance.status = "busy" if normalize_status(ambulance.status) == "available" else "available"
            ambulance.updated_at = datetime.now(timezone.utc)
        db.commit()
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


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
