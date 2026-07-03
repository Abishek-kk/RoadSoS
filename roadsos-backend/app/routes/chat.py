from fastapi import APIRouter
from pydantic import BaseModel
import anyio

from app.ai.rag_pipeline import run_rag_pipeline
from app.ai.retrieval import NUMBER_WORDS, normalize, requested_limit, tokenize


router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatPayload(BaseModel):
    messages: list[ChatMessage]
    lat: float | None = None
    lng: float | None = None


@router.post("")
async def chat(payload: ChatPayload):
    user_message = latest_user_message(payload.messages)
    if not user_message:
        return response_payload(
            reply="Tell me what happened, and I will guide you through the safest next steps.",
            intent="general",
            used_llm=False,
            lat=payload.lat,
            lng=payload.lng,
        )

    is_followup = is_more_followup(user_message)
    effective_message = expand_followup(user_message, payload.messages)
    if is_greeting(user_message):
        return response_payload(
            reply=(
                "Hi, I am RoadSoS AI. I can help with nearby hospitals, police stations, "
                "towing services, road alerts, first-aid, SOS steps, and driving safety. What do you need right now?"
            ),
            intent="general",
            used_llm=False,
            lat=payload.lat,
            lng=payload.lng,
        )

    use_llm = should_use_llm(effective_message)
    try:
        with anyio.fail_after(20):
            result = await anyio.to_thread.run_sync(
                lambda: run_rag_pipeline(
                    effective_message,
                    messages=[message.model_dump() for message in payload.messages],
                    lat=payload.lat,
                    lng=payload.lng,
                    use_llm=use_llm,
                    skip=3 if is_followup and requested_limit(user_message, default=0) == 0 else 0,
                )
            )
    except TimeoutError:
        result = run_rag_pipeline(
            effective_message,
            messages=[message.model_dump() for message in payload.messages],
            lat=payload.lat,
            lng=payload.lng,
            use_llm=False,
            skip=3 if is_followup and requested_limit(user_message, default=0) == 0 else 0,
        )
    return response_payload(
        reply=result.reply,
        intent=result.intent,
        used_llm=result.used_llm,
        lat=payload.lat,
        lng=payload.lng,
        emergency_detected=bool(result.emergency and result.emergency.get("detected")),
    )


def latest_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()
    return ""


def expand_followup(message: str, messages: list[ChatMessage]) -> str:
    normalized = normalize(message)
    if not is_more_followup(message):
        return message

    previous_users = [
        item.content.strip()
        for item in messages
        if item.role == "user" and item.content.strip() and item.content.strip() != message
    ]
    if not previous_users:
        return message
    return f"{previous_users[-1]} {message}"


def is_more_followup(message: str) -> bool:
    normalized = normalize(message)
    if normalized in {
        "any other",
        "other",
        "more",
        "another",
        "show more",
        "anything else",
        "next",
    }:
        return True
    return requested_limit(message, default=0) > 0 and len(tokenize(message) - set(NUMBER_WORDS)) <= 2


def is_greeting(message: str) -> bool:
    return normalize(message) in {"hi", "hello", "hey", "hai", "hii", "yo"}


def should_use_llm(message: str) -> bool:
    normalized = normalize(message)
    tokens = tokenize(normalized)
    listing_terms = {
        "hospitals",
        "stations",
        "contacts",
        "services",
        "nearby",
        "nearest",
        "list",
        "show",
    }
    emergency_terms = {"accident", "crash", "bleeding", "fire", "ambulance", "sos"}
    if tokens & emergency_terms:
        return True
    return not bool(tokens & listing_terms and requested_limit(message, default=0) > 0)


def response_payload(
    reply: str,
    intent: str,
    used_llm: bool,
    lat: float | None,
    lng: float | None,
    emergency_detected: bool = False,
) -> dict:
    return {
        "reply": reply,
        "intent": intent,
        "used_llm": used_llm,
        "suggestions": suggested_prompts(intent, lat=lat, lng=lng, emergency_detected=emergency_detected),
    }


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
