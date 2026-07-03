from __future__ import annotations

from typing import Any, Iterable

from app.services.structured_service import StructuredEmergencyService


class TowingService(StructuredEmergencyService):
    dataset_name = "towing.json"
    category = "towing_service"
    fallback_phone = "112"
    default_radius_km = 50.0
    average_speed_kmph = 30.0

    def __init__(self, rows: Iterable[dict[str, Any]] | None = None) -> None:
        super().__init__(rows=rows)

    def format_result(self, row: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
        result = super().format_result(row, fallback_reason=fallback_reason)
        open_24x7 = row.get("open_24x7")
        if open_24x7 is True:
            availability = "24x7"
        elif open_24x7 is False:
            availability = "Availability not stored"
        else:
            availability = row.get("availability") or "Availability not stored"
        result["availability"] = availability
        result["rating"] = row.get("rating")
        return result
