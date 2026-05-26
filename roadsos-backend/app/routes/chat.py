import re
from dataclasses import dataclass

from fastapi import APIRouter
from pydantic import BaseModel

from app.ai.gemini_client import generate_chat_response
from app.config import get_gemini_api_key
from app.routes._data import distance_km, load_json, with_distance


router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatPayload(BaseModel):
    messages: list[ChatMessage]
    lat: float | None = None
    lng: float | None = None


@dataclass
class ContextChunk:
    title: str
    body: str
    score: int = 0


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "me",
    "my",
    "near",
    "of",
    "on",
    "or",
    "please",
    "should",
    "the",
    "to",
    "what",
    "when",
    "where",
    "with",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

SYSTEM_INSTRUCTION = """
You are RoadSoS AI, a concise road-safety and emergency assistant for India.
Use the provided context first. Give practical, ordered steps.
For urgent medical, crash, fire, or police situations, tell the user to call 112/108 first.
Do not invent phone numbers, distances, or official facts that are not in context.
Keep the answer under 160 words unless the user asks for detail.
"""


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

    context_chunks = retrieve_context(effective_message, payload.lat, payload.lng)
    context = "\n\n".join(f"{chunk.title}\n{chunk.body}" for chunk in context_chunks)

    if get_gemini_api_key():
        reply = generate_chat_response(
            prompt=conversation_prompt(payload.messages),
            context=context,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        if reply and not reply.lower().startswith("error:"):
            return {"reply": reply.strip()}

    limit_override = requested_limit(user_message, default=0) or None
    return {
        "reply": build_fallback_reply(
            effective_message,
            context_chunks,
            skip=3 if is_followup and limit_override is None else 0,
            limit_override=limit_override,
        )
    }


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


def conversation_prompt(messages: list[ChatMessage]) -> str:
    recent = messages[-6:]
    return "\n".join(f"{message.role}: {message.content}" for message in recent)


def retrieve_context(question: str, lat: float | None = None, lng: float | None = None) -> list[ContextChunk]:
    tokens = tokenize(question)
    normalized_question = normalize(question)
    intent = detect_intent(normalized_question)
    chunks = knowledge_chunks(lat, lng)

    for chunk in chunks:
        title = normalize(chunk.title)
        text = normalize(f"{chunk.title} {chunk.body}")
        chunk.score = sum(weight_for_token(token) for token in tokens if token in text)
        chunk.score += sum(weight_for_token(token) for token in tokens if token in title)
        for phrase in important_phrases(normalized_question):
            if phrase in text:
                chunk.score += 12
            if phrase in title:
                chunk.score += 10
        chunk.score += intent_boost(intent, chunk.title)
        if intent in {"hospital", "police", "towing", "alert"}:
            chunk.score += distance_boost(chunk.body)

    ranked = sorted(chunks, key=lambda chunk: chunk.score, reverse=True)
    if intent in {"hospital", "police", "towing", "alert"}:
        ranked = filter_intent_chunks(intent, ranked)
        return ranked

    selected = [
        chunk
        for chunk in ranked
        if chunk.score > 0 and not chunk.title.startswith(("Hospitals:", "Police:", "Road Alert:"))
    ][:5]
    return selected or ranked[:3]


def detect_intent(text: str) -> str:
    if "police" in text:
        return "police"
    if "tow" in text or "towing" in text or "recovery" in text or "breakdown" in text:
        return "towing"
    if "hospital" in text or "ambulance" in text or "doctor" in text:
        return "hospital"
    if "alert" in text or "traffic" in text or re.search(r"\bnh\s*\d+\b", text):
        return "alert"
    return "general"


def intent_boost(intent: str, title: str) -> int:
    title = title.lower()
    if intent == "police":
        return 35 if title.startswith("police:") else -8
    if intent == "hospital":
        return 35 if title.startswith("hospitals:") else -8
    if intent == "towing":
        return 35 if title.startswith("towing:") else -8
    if intent == "alert":
        return 35 if title.startswith("road alert:") else -8
    return 0


def filter_intent_chunks(intent: str, chunks: list[ContextChunk]) -> list[ContextChunk]:
    prefix = {
        "hospital": "Hospitals:",
        "police": "Police:",
        "towing": "Towing:",
        "alert": "Road Alert:",
    }[intent]
    return [chunk for chunk in chunks if chunk.title.startswith(prefix)]


def distance_boost(body: str) -> int:
    match = re.search(r"Distance: ([0-9.]+) km", body)
    if not match:
        return 0
    distance = float(match.group(1))
    return max(0, int(30 - distance))


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in STOP_WORDS
    }


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def important_phrases(text: str) -> list[str]:
    phrases = [
        "tyre burst",
        "tire burst",
        "brake failure",
        "bleeding",
        "severe bleeding",
        "heavy bleeding",
        "head injury",
        "road accident",
        "vehicle fire",
        "waterlogged roads",
        "nh 48",
        "nh 44",
        "nh 19",
        "chennai",
        "mumbai",
        "delhi",
        "bengaluru",
        "hyderabad",
    ]
    return [phrase for phrase in phrases if phrase in text]


def weight_for_token(token: str) -> int:
    emergency_terms = {
        "accident",
        "ambulance",
        "bleeding",
        "brake",
        "burn",
        "crash",
        "fire",
        "fracture",
        "hospital",
        "police",
        "towing",
        "sos",
        "tow",
        "towing",
        "tyre",
        "tire",
        }
    return 4 if token in emergency_terms else 1


def knowledge_chunks(lat: float | None = None, lng: float | None = None) -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    chunks.extend(text_file_chunks("emergency_guides.txt"))
    chunks.extend(text_file_chunks("safety_rules.txt"))
    chunks.extend(alert_chunks(lat, lng))
    chunks.extend(place_chunks("Hospitals", "hospitals.json", lat, lng))
    chunks.extend(place_chunks("Police", "police_stations.json", lat, lng))
    chunks.extend(place_chunks("Towing", "towing.json", lat, lng))
    return chunks


def text_file_chunks(filename: str) -> list[ContextChunk]:
    path = load_text_path(filename)
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"\n(?=GUIDE \d+:|=== SECTION \d+:)", text)
    chunks = []
    for section in sections:
        clean = "\n".join(line.strip() for line in section.splitlines() if line.strip())
        if len(clean) < 80:
            continue
        title = clean.splitlines()[0][:90]
        chunks.append(ContextChunk(title=title, body=clean[:5000]))
    return chunks


def load_text_path(filename: str):
    from app.routes._data import DATA_DIR

    return DATA_DIR / filename


def alert_chunks(lat: float | None = None, lng: float | None = None) -> list[ContextChunk]:
    chunks = []
    for alert in load_json("road_alerts.json"):
        location = alert["location"]
        distance = ""
        if lat is not None and lng is not None:
            km = distance_km(lat, lng, location["lat"], location["lng"])
            distance = f" Distance: {km} km."
        body = (
            f"{alert['title']}. Severity: {alert['severity']}. Status: {alert['status']}. "
            f"Road: {alert['road']}, {alert['direction']}. Location: {location['address']}. "
            f"{distance} Details: {alert['description']} Detour: {alert.get('detour') or 'No detour listed'}."
        )
        chunks.append(ContextChunk(title=f"Road Alert: {alert['title']}", body=body))
    return chunks


def place_chunks(title: str, filename: str, lat: float | None = None, lng: float | None = None) -> list[ContextChunk]:
    chunks = []
    for place in with_distance(load_json(filename), lat, lng):
        phone = place.get("emergency_phone") or place.get("phone")
        city = place.get("city") or place.get("district") or "nearby area"
        distance = ""
        if place.get("distance_km") is not None:
            distance = f" Distance: {place['distance_km']} km."
        body = (
            f"{place['name']} in {city}, {place['state']}. "
            f"Address: {place['address']}. Phone: {phone}. "
            f"Open 24x7: {place.get('open_24x7', 'unknown')}.{distance}"
        )
        if "specialties" in place:
            body += f" Specialties: {', '.join(place['specialties'])}."
        if "jurisdiction" in place:
            body += f" Jurisdiction: {place['jurisdiction']}."
        chunks.append(ContextChunk(title=f"{title}: {place['name']}", body=body))
    return chunks


def build_fallback_reply(
    question: str,
    chunks: list[ContextChunk],
    skip: int = 0,
    limit_override: int | None = None,
) -> str:
    lower = question.lower()
    intent = detect_intent(normalize(question))

    if intent in {"hospital", "police", "towing", "alert"}:
        return build_listing_reply(intent, chunks, question, skip, limit_override)

    intro = "Based on the RoadSoS safety knowledge base:"

    if any(word in lower for word in ["accident", "crash", "injured", "bleeding", "fire"]):
        intro = "Call 112 or 108 first. Then:"
    elif any(word in lower for word in ["hospital", "ambulance", "doctor"]):
        intro = "For medical help, call 108. Relevant RoadSoS data:"
    elif "police" in lower:
        intro = "For immediate police help, call 100 or 112. Relevant RoadSoS data:"
    elif "tow" in lower or "breakdown" in lower:
        intro = "For a breakdown or towing need, move to a safe spot first. Relevant RoadSoS data:"

    bullets = []
    for chunk in chunks[:3]:
        summary = summarize_relevant(chunk.body, question)
        bullets.append(f"- {summary}")

    if not bullets:
        bullets.append("- Share what happened, your location, and whether anyone is injured.")

    return f"{intro}\n" + "\n".join(bullets)


def build_listing_reply(
    intent: str,
    chunks: list[ContextChunk],
    question: str,
    skip: int = 0,
    limit_override: int | None = None,
) -> str:
    limit = limit_override or requested_limit(question, default=4)
    selected = chunks[skip : skip + limit] or chunks[:limit]
    rows = [format_listing_row(chunk.body) for chunk in selected]
    rows = [row for row in rows if row]

    if intent == "hospital":
        intro = "Here are the most relevant hospitals I found. For an emergency, call 108 first:"
    elif intent == "police":
        intro = "Here are the most relevant police contacts. For immediate help, call 100 or 112:"
    elif intent == "towing":
        intro = "Here are the nearest towing services I found. If you are in danger on the road, call 112 first:"
    else:
        intro = "Here are the relevant road alerts from the RoadSoS data:"

    if not rows:
        return "I could not find a matching record. Tell me your city, highway, or current location and I will narrow it down."

    return intro + "\n" + "\n".join(f"- {row}" for row in rows)


def requested_limit(question: str, default: int = 4) -> int:
    normalized = normalize(question)
    if any(word in normalized.split() for word in ["all", "every", "full"]):
        return 50

    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b(?:any|top|show|give|list)?\s*{word}\b", normalized):
            return value

    match = re.search(r"\btop\s+(\d+)\b|\b(\d+)\s+(?:nearby\s+)?(?:hospitals?|police|towing|tow|alerts?)\b", normalized)
    if not match:
        return default

    value = int(match.group(1) or match.group(2))
    return max(1, min(value, 50))


def format_listing_row(text: str) -> str:
    cleaned = summarize(text)
    distance = re.search(r"Distance: ([0-9.]+) km", text)
    phone = re.search(r"Phone: ([^\.]+)", text)
    extras = []
    if distance:
        extras.append(f"{distance.group(1)} km away")
    if phone:
        extras.append(f"phone {phone.group(1).strip()}")
    if extras:
        return f"{cleaned} ({', '.join(extras)})"
    return cleaned


def summarize(text: str) -> str:
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("===") or re.match(r"^GUIDE \d+:", clean):
            continue
        lines.append(clean)
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(lines))
    useful = [sentence.strip() for sentence in sentences if len(sentence.strip()) > 30]
    return " ".join(useful[:2])[:420]


def summarize_relevant(text: str, question: str) -> str:
    sentences = split_clean_sentences(text)
    tokens = tokenize(question)
    scored = []
    for index, sentence in enumerate(sentences):
        normalized_sentence = normalize(sentence)
        score = sum(weight_for_token(token) for token in tokens if token in normalized_sentence)
        for phrase in important_phrases(normalize(question)):
            if phrase in normalized_sentence:
                score += 12
        scored.append((score, -index, sentence))

    best = [item[2] for item in sorted(scored, reverse=True) if item[0] > 0][:2]
    if best:
        return " ".join(best)[:420]
    return summarize(text)


def split_clean_sentences(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean.startswith("===") or re.match(r"^GUIDE \d+:", clean):
            continue
        lines.append(clean)
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", " ".join(lines))
        if len(sentence.strip()) > 30
    ]
