from __future__ import annotations

import asyncio
import json
import logging
from queue import Queue
from typing import Any

import anyio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.rag_pipeline import run_rag_pipeline
from app.dependencies import DbSession
from app.routes._data import reverse_geocode
from db import crud


router = APIRouter(prefix="/chat", tags=["Chat"])
CHAT_LLM_TIMEOUT_SECONDS = 120
logger = logging.getLogger("roadsos.chat")
REVERSE_GEOCODE_CACHE: dict[tuple[float, float], str | None] = {}
REVERSE_GEOCODE_IN_FLIGHT: set[tuple[float, float]] = set()
CURRENT_LOCATION_PHRASES = (
    "current location",
    "my location",
    "where am i",
    "where i am",
    "where are we",
    "which city",
    "what city",
    "which town",
    "which village",
    "where exactly",
)


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
    apply_latest_location_if_missing(payload, db)
    location_name = await resolve_location_name(payload, user_message, allow_remote=True)
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


@router.post("/stream")
async def chat_stream(payload: ChatPayload, db: Session = DbSession):
    user_message = latest_user_message(payload.messages)
    apply_latest_location_if_missing(payload, db)
    location_name = await resolve_location_name(payload, user_message, allow_remote=False)
    emergency_contacts = load_emergency_contacts(db)

    return StreamingResponse(
        stream_chat_events(payload, user_message, location_name, emergency_contacts),
        media_type="application/x-ndjson",
    )


async def stream_chat_events(
    payload: ChatPayload,
    user_message: str,
    location_name: str | None,
    emergency_contacts: list[dict[str, Any]],
):
    event_queue: Queue[dict[str, Any] | None] = Queue()

    def emit(event: dict[str, Any]) -> None:
        event_queue.put(event)

    def on_token(token: str) -> None:
        if token:
            emit({"type": "token", "content": token})

    def worker() -> None:
        try:
            result = run_rag_pipeline(
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
                on_token=on_token,
            )
            emit(
                {
                    "type": "done",
                    "result": response_payload(
                        reply=result.reply,
                        intent=result.intent,
                        used_llm=result.used_llm,
                        llm_provider=getattr(result, "llm_provider", "none"),
                        lat=payload.lat,
                        lng=payload.lng,
                        emergency_detected=bool(result.emergency and result.emergency.get("detected")),
                        retrieval_confidence=getattr(result, "retrieval_confidence", None),
                        sources=[source.as_dict() for source in getattr(result, "sources", [])],
                    ),
                }
            )
        except Exception as exc:
            logger.error("Streaming chat failed: %s", exc, exc_info=True)
            emit(
                {
                    "type": "error",
                    "message": "The RoadSoS backend had trouble streaming that response. Please try again.",
                }
            )
        finally:
            event_queue.put(None)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(anyio.to_thread.run_sync, worker)
        while True:
            event = await anyio.to_thread.run_sync(event_queue.get)
            if event is None:
                break
            yield json.dumps(event) + "\n"
        task_group.cancel_scope.cancel()


async def resolve_location_name(
    payload: ChatPayload,
    user_message: str = "",
    allow_remote: bool = True,
) -> str | None:
    location_name = (payload.location_name or "").strip()
    if location_name:
        return location_name
    location_label = location_label_from_payload(payload)
    if location_label:
        return location_label
    if payload.lat is None or payload.lng is None:
        return None
    if not should_reverse_geocode_for_chat(user_message):
        logger.info("Skipping backend reverse geocode for chat; location label is not required for this query.")
        return None

    cache_key = (round(float(payload.lat), 5), round(float(payload.lng), 5))
    if cache_key in REVERSE_GEOCODE_CACHE:
        cached = REVERSE_GEOCODE_CACHE[cache_key]
        if cached or not allow_remote:
            return cached
    if not allow_remote:
        schedule_reverse_geocode_cache(payload.lat, payload.lng)
        return None

    resolved = await reverse_geocode(payload.lat, payload.lng)
    REVERSE_GEOCODE_CACHE[cache_key] = resolved
    return resolved


def schedule_reverse_geocode_cache(lat: float, lng: float) -> None:
    cache_key = (round(float(lat), 5), round(float(lng), 5))
    if cache_key in REVERSE_GEOCODE_CACHE or cache_key in REVERSE_GEOCODE_IN_FLIGHT:
        return
    REVERSE_GEOCODE_IN_FLIGHT.add(cache_key)
    try:
        asyncio.get_running_loop().create_task(cache_reverse_geocode(lat, lng, cache_key))
    except RuntimeError:
        REVERSE_GEOCODE_IN_FLIGHT.discard(cache_key)


async def cache_reverse_geocode(lat: float, lng: float, cache_key: tuple[float, float]) -> None:
    try:
        REVERSE_GEOCODE_CACHE[cache_key] = await reverse_geocode(lat, lng)
    finally:
        REVERSE_GEOCODE_IN_FLIGHT.discard(cache_key)


def location_label_from_payload(payload: ChatPayload) -> str | None:
    parts = []
    seen = set()
    for value in (payload.city, payload.state, payload.country):
        cleaned = (value or "").strip()
        if not cleaned:
            continue
        normalized = cleaned.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        parts.append(cleaned)
    return ", ".join(parts) if parts else None


def apply_latest_location_if_missing(payload: ChatPayload, db: Session) -> None:
    if payload.lat is not None and payload.lng is not None:
        return
    if not hasattr(db, "query"):
        return
    user = crud.get_system_user(db)
    if not user:
        return
    latest = crud.get_latest_user_location(db, user.id)
    if not latest:
        return
    payload.lat = latest.lat
    payload.lng = latest.lng


def should_reverse_geocode_for_chat(user_message: str) -> bool:
    normalized = " ".join((user_message or "").lower().split())
    if not normalized:
        return False
    if any(phrase in normalized for phrase in CURRENT_LOCATION_PHRASES):
        return True
    if "location" in normalized and any(term in normalized for term in ("my", "current", "where")):
        return True
    if "city" in normalized and any(term in normalized for term in ("my", "which", "what", "where")):
        return True
    return False


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
    response_source: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reply": reply,
        "intent": intent,
        "used_llm": used_llm,
        "llm_provider": llm_provider,
        "suggestions": suggested_prompts(intent, lat=lat, lng=lng, emergency_detected=emergency_detected),
    }
    # response_source: one of 'direct' (deterministic), 'llm' (AI), 'fallback' (LLM attempted but failed)
    payload["response_source"] = response_source
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
