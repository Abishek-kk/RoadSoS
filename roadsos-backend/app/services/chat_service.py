from __future__ import annotations

from typing import Any

from app.services.rag_service import RagResult, run_rag_pipeline


def run_chat_pipeline(
    question: str,
    messages: list[dict[str, str]] | None = None,
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
    current_datetime: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    radius_km: float | None = None,
    nearby_places: list[dict[str, Any]] | None = None,
    emergency_contacts: list[dict[str, Any]] | None = None,
) -> RagResult:
    return run_rag_pipeline(
        question=question,
        messages=messages,
        lat=lat,
        lng=lng,
        location_name=location_name,
        current_datetime=current_datetime,
        city=city,
        state=state,
        country=country,
        radius_km=radius_km,
        nearby_places=nearby_places,
        emergency_contacts=emergency_contacts,
    )
