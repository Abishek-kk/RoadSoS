from __future__ import annotations

from typing import Any, Iterable

from app.services.structured_service import StructuredEmergencyService


BAD_HOSPITAL_COORDINATE_ROWS = {
    "TN00868",
    "TN00885",
    "TN00918",
    "TN00922",
    "TN00940",
    "TN00989",
    "TN00998",
}


class HospitalService(StructuredEmergencyService):
    dataset_name = "hospitals.json"
    category = "hospital"
    fallback_phone = "108"
    default_radius_km = 25.0
    average_speed_kmph = 35.0

    def __init__(self, rows: Iterable[dict[str, Any]] | None = None) -> None:
        super().__init__(rows=rows)

    def load_database(self) -> list[dict[str, Any]]:
        return [
            row
            for row in super().load_database()
            if row.get("id") not in BAD_HOSPITAL_COORDINATE_ROWS
        ]

    def format_result(self, row: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
        result = super().format_result(row, fallback_reason=fallback_reason)
        result["specialties"] = row.get("specialties") or []
        return result
