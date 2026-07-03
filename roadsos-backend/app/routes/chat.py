from __future__ import annotations

from typing import Any

import anyio
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.rag_pipeline import run_rag_pipeline
from app.dependencies import DbSession
from app.routes._data import reverse_geocode
from db import crud


router = APIRouter(prefix="/chat", tags=["Chat"])
CHAT_LLM_TIMEOUT_SECONDS = 120


class ChatMessage(BaseModel):
    role: str
    content: str


class NearbyPlacePayload(BaseModel):
    name: str
    category: str
    distance_km: float | None = None
    address: str
    phone: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None


class ChatPayload(BaseModel):
    messages: list[ChatMessage]
    lat: float | None = None
    lng: float | None = None
    location_name: str | None = None
    current_datetime: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    radius_km: float | None = None
    nearby_places: list[NearbyPlacePayload] | None = None


@router.post("")
async def chat(payload: ChatPayload, db: Session = DbSession):
    user_message = latest_user_message(payload.messages)
    location_name = await resolve_location_name(payload)
    emergency_contacts = load_emergency_contacts(db)

    try:
        with anyio.fail_after(CHAT_LLM_TIMEOUT_SECONDS):
            result = await anyio.to_thread.run_sync(
                lambda: run_rag_pipeline(
                    user_message,
                    messages=[message.model_dump() for message in payload.messages],
                    lat=payload.lat,
                    lng=payload.lng,
                    location_name=location_name,
                    current_datetime=payload.current_datetime,
                    city=payload.city,
                    state=payload.state,
                    country=payload.country,
                    radius_km=payload.radius_km,
                    nearby_places=[place.model_dump() for place in (payload.nearby_places or [])],
                    emergency_contacts=emergency_contacts,
                )
            )
    except TimeoutError:
        return response_payload(
            reply=(
                "I could not complete the AI response in time. "
                "Please try again, and call 112 immediately if this is urgent."
            ),
            intent="general",
            used_llm=False,
            llm_provider="none",
            lat=payload.lat,
            lng=payload.lng,
            emergency_detected=False,
        )

    return response_payload(
        reply=result.reply,
        intent=result.intent,
        used_llm=result.used_llm,
        llm_provider=getattr(result, "llm_provider", "none"),
        lat=payload.lat,
        lng=payload.lng,
        emergency_detected=bool(result.emergency and result.emergency.get("detected")),
        retrieval_confidence=getattr(result, "retrieval_confidence", None),
        sources=[source.as_dict() for source in getattr(result, "sources", [])],
    )


async def resolve_location_name(payload: ChatPayload) -> str | None:
    location_name = (payload.location_name or "").strip()
    if location_name:
        return location_name
    if payload.lat is None or payload.lng is None:
        return None
    return await reverse_geocode(payload.lat, payload.lng)


def latest_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def load_emergency_contacts(db: Session) -> list[dict[str, Any]]:
    if not hasattr(db, "query"):
        return []
    user = crud.get_system_user(db)
    if not user:
        return []
    return [
        {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "relation": contact.relation,
            "notify_sms": contact.notify_sms,
            "notify_whatsapp": contact.notify_whatsapp,
            "notify_call": contact.notify_call,
        }
        for contact in crud.get_emergency_contacts(db, user.id)
    ]


def response_payload(
    reply: str,
    intent: str,
    used_llm: bool,
    llm_provider: str,
    lat: float | None,
    lng: float | None,
    emergency_detected: bool = False,
    retrieval_confidence: float | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reply": reply,
        "intent": intent,
        "used_llm": used_llm,
        "llm_provider": llm_provider,
        "suggestions": suggested_prompts(intent, lat=lat, lng=lng, emergency_detected=emergency_detected),
    }
    if retrieval_confidence is not None:
        payload["retrieval_confidence"] = retrieval_confidence
    if sources is not None:
        payload["sources"] = sources
    return payload


def suggested_prompts(
    intent: str,
    lat: float | None = None,
    lng: float | None = None,
    emergency_detected: bool = False,
) -> list[str]:
    has_location = lat is not None and lng is not None
    if emergency_detected:
        return [
            "What should I tell the emergency operator?",
            "How do I keep the injured person safe?",
            "Find nearest hospital",
        ]
    if intent == "hospital":
        return ["Show top 5 hospitals", "What should I do before ambulance arrives?", "Find police nearby"]
    if intent == "police":
        return ["What details should I report?", "Find nearest hospital", "Call SOS steps"]
    if intent == "towing":
        return ["How do I stay safe while waiting?", "Show more towing options", "What if I am on a highway?"]
    if intent == "alert":
        return ["Explain this risk", "Find safer route tips", "Show nearby police"]
    if not has_location:
        return ["Find nearby hospitals", "What to do after an accident?", "How to use SOS safely?"]
    return ["Check road risk near me", "Find nearby police", "First-aid for bleeding"]
