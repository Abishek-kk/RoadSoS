from __future__ import annotations

from typing import Any, Iterable

from app.services.structured_service import StructuredEmergencyService


class PoliceService(StructuredEmergencyService):
    dataset_name = "police_stations.json"
    category = "police_station"
    fallback_phone = "100"
    default_radius_km = 25.0
    average_speed_kmph = 40.0

    def __init__(self, rows: Iterable[dict[str, Any]] | None = None) -> None:
        super().__init__(rows=rows)

    def format_result(self, row: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
        result = super().format_result(row, fallback_reason=fallback_reason)
        result["officer"] = (
            row.get("officer")
            or row.get("station_officer")
            or row.get("in_charge")
            or row.get("sho")
            or "Officer in charge not listed"
        )
        result["zone"] = row.get("zone")
        result["jurisdiction"] = row.get("jurisdiction")
        return result
