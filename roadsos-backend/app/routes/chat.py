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
        return {"reply": "Tell me what happened, and I will guide you through the safest next steps."}

    is_followup = is_more_followup(user_message)
    effective_message = expand_followup(user_message, payload.messages)
    if is_greeting(user_message):
        return {
            "reply": (
                "Hi, I am RoadSoS AI. I can help with nearby hospitals, police stations, "
                "towing services, road alerts, first-aid, SOS steps, and driving safety. What do you need right now?"
            )
        }

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
    return {"reply": result.reply}


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
    instant_terms = {
        "hospital",
        "hospitals",
        "police",
        "station",
        "stations",
        "tow",
        "towing",
        "mechanic",
        "nearby",
        "nearest",
        "alert",
        "alerts",
        "danger",
        "accident",
        "crash",
        "bleeding",
        "fire",
        "ambulance",
        "sos",
        "help",
    }
    return not bool(tokens & instant_terms)
