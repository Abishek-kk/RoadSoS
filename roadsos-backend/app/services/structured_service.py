from __future__ import annotations

import math
import re
from typing import Any, Iterable

from app.algorithms.haversine import distance_km
from app.routes._data import clean_phone_number, load_json, normalize_coordinates


DEFAULT_ETA_SPEED_KMPH = 35.0


class StructuredEmergencyService:
    """Base class for verified local emergency-service datasets."""

    dataset_name: str = ""
    category: str = "service"
    fallback_phone: str = "112"
    default_radius_km: float = 25.0
    average_speed_kmph: float = DEFAULT_ETA_SPEED_KMPH

    def __init__(self, rows: Iterable[dict[str, Any]] | None = None) -> None:
        self._rows_override = list(rows) if rows is not None else None

    def load_database(self) -> list[dict[str, Any]]:
        rows = self._rows_override if self._rows_override is not None else load_json(self.dataset_name)
        return [normalize_coordinates(dict(row)) for row in rows if isinstance(row, dict)]

    def search_by_district(self, district: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._search_field("district", district, limit=limit)

    def search_by_city(self, city: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._search_field("city", city, limit=limit)

    def search_by_pincode(self, pincode: str, limit: int = 20) -> list[dict[str, Any]]:
        target = normalize_digits(pincode)
        if not target:
            return []
        matches = [
            row
            for row in self.load_database()
            if normalize_digits(row.get("pincode")) == target
            or target in normalize_digits(row.get("address"))
        ]
        return [self.format_result(row) for row in matches[:limit]]

    def search_by_coordinates(
        self,
        lat: float,
        lng: float,
        radius_km: float | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        return self.find_nearest(lat, lng, limit=limit, radius_km=radius_km)

    def find_nearest(
        self,
        lat: float,
        lng: float,
        limit: int = 3,
        radius_km: float | None = None,
    ) -> list[dict[str, Any]]:
        ranked = self._rank_by_distance(lat, lng)
        requested_radius = self.default_radius_km if radius_km is None else float(radius_km)
        within_radius = [
            row
            for row in ranked
            if row.get("distance_km") is not None and float(row["distance_km"]) <= requested_radius
        ]
        selected = within_radius[:limit]
        fallback_used = False
        if not selected:
            selected = ranked[:limit]
            fallback_used = bool(selected)

        return [
            self.format_result(
                row,
                fallback_reason=(
                    f"No {self.category.replace('_', ' ')} was found within {format_number(requested_radius)} km; "
                    "returning the nearest verified local entry."
                )
                if fallback_used
                else None,
            )
            for row in selected
        ]

    def find_one(self, lat: float, lng: float, radius_km: float | None = None) -> dict[str, Any] | None:
        results = self.find_nearest(lat, lng, limit=1, radius_km=radius_km)
        return results[0] if results else None

    def format_result(self, row: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
        distance = parse_float(row.get("distance_km"))
        eta_minutes = estimate_eta_minutes(distance, self.average_speed_kmph)
        lat = parse_float(row.get("lat"))
        lng = parse_float(row.get("lng"))
        phone = clean_phone_number(row.get("emergency_phone") or row.get("phone"), self.fallback_phone)
        result: dict[str, Any] = {
            "id": row.get("id") or stable_id(row),
            "name": row.get("name") or row.get("station_name") or self.category.replace("_", " ").title(),
            "category": self.category,
            "type": row.get("type"),
            "address": row.get("address") or "Address not listed",
            "city": row.get("city"),
            "district": row.get("district"),
            "state": row.get("state"),
            "country": row.get("country") or "India",
            "pincode": row.get("pincode"),
            "lat": lat,
            "lng": lng,
            "gps": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
            "phone": phone,
            "emergency_phone": clean_phone_number(row.get("emergency_phone"), self.fallback_phone),
            "distance_km": distance,
            "eta_minutes": eta_minutes,
            "eta": format_eta(eta_minutes),
            "open_24x7": row.get("open_24x7"),
            "call_url": f"tel:{phone}",
        }
        if lat is not None and lng is not None:
            result["directions_url"] = f"https://www.openstreetmap.org/directions?to={lat}%2C{lng}"
        if fallback_reason:
            result["fallback_reason"] = fallback_reason
        return result

    def _search_field(self, field: str, value: str, limit: int = 20) -> list[dict[str, Any]]:
        target = normalize_text(value)
        if not target:
            return []
        matches = []
        for row in self.load_database():
            field_value = normalize_text(row.get(field))
            if field_value == target or target in field_value:
                matches.append(row)
        return [self.format_result(row) for row in matches[:limit]]

    def _rank_by_distance(self, lat: float, lng: float) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for row in self.load_database():
            row_lat = parse_float(row.get("lat"))
            row_lng = parse_float(row.get("lng"))
            if row_lat is None or row_lng is None:
                continue
            ranked.append({**row, "distance_km": distance_km(lat, lng, row_lat, row_lng)})
        ranked.sort(
            key=lambda row: (
                row.get("distance_km") is None,
                float(row["distance_km"]) if row.get("distance_km") is not None else math.inf,
                str(row.get("name") or row.get("station_name") or "").lower(),
            )
        )
        return ranked


def estimate_eta_minutes(distance: float | None, speed_kmph: float = DEFAULT_ETA_SPEED_KMPH) -> int | None:
    if distance is None:
        return None
    speed = max(float(speed_kmph), 1.0)
    return max(1, int(math.ceil((float(distance) / speed) * 60)))


def format_eta(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    remainder = minutes % 60
    if remainder == 0:
        return f"{hours} hr"
    return f"{hours} hr {remainder} min"


def parse_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalize_digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def stable_id(row: dict[str, Any]) -> str:
    name = normalize_text(row.get("name") or row.get("station_name") or "service")
    lat = row.get("lat") or row.get("latitude") or ""
    lng = row.get("lng") or row.get("longitude") or ""
    return f"{name}-{lat}-{lng}".strip("-").replace(" ", "-")


def format_number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")
