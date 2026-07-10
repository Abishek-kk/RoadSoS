from __future__ import annotations

from typing import Any, Iterable

from app.services.structured_service import StructuredEmergencyService


class ShowroomService(StructuredEmergencyService):
    dataset_name = "showrooms.json"
    category = "showroom"
    fallback_phone = "112"
    default_radius_km = 25.0
    average_speed_kmph = 35.0

    def __init__(self, rows: Iterable[dict[str, Any]] | None = None) -> None:
        super().__init__(rows=rows)

    def format_result(self, row: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
        result = super().format_result(row, fallback_reason=fallback_reason)
        result["zone"] = row.get("zone")
        result["source"] = row.get("source")
        result["verification_status"] = row.get("verification_status")
        return result
