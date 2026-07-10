from __future__ import annotations

from typing import Any, Iterable

from app.services.structured_service import StructuredEmergencyService


class PunctureShopService(StructuredEmergencyService):
    dataset_name = "puncture_shops.json"
    category = "puncture_shop"
    fallback_phone = "112"
    default_radius_km = 25.0
    average_speed_kmph = 35.0

    def __init__(self, rows: Iterable[dict[str, Any]] | None = None) -> None:
        super().__init__(rows=rows)

    def format_result(self, row: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
        result = super().format_result(row, fallback_reason=fallback_reason)
        open_24x7 = row.get("open_24x7")
        if open_24x7 is True:
            availability = "24x7"
        elif row.get("status"):
            availability = str(row["status"])
        else:
            availability = "Availability not stored"
        result["availability"] = availability
        result["services"] = row.get("services") or []
        result["vehicle_types"] = row.get("vehicle_types") or []
        result["rating"] = row.get("rating")
        result["status"] = row.get("status")
        return result
