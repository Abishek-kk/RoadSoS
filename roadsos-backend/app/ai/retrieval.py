"""
retrieval.py - lightweight RAG retrieval for RoadSoS.

Builds context chunks from local RoadSoS data and ranks them with deterministic
keyword, intent, phrase, and distance signals. This keeps chat useful even when
LLM or embedding services are unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.routes._data import DATA_DIR, distance_km, load_json, with_distance


@dataclass
class ContextChunk:
    title: str
    body: str
    score: int = 0
    metadata: dict[str, Any] | None = None


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "can",
    "for",
    "from",
    "give",
    "how",
    "i",
    "in",
    "is",
    "list",
    "me",
    "my",
    "near",
    "nearby",
    "of",
    "on",
    "or",
    "please",
    "should",
    "show",
    "the",
    "to",
    "top",
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

INTENT_PREFIX = {
    "hospital": "Hospitals:",
    "police": "Police:",
    "towing": "Towing:",
    "alert": "Road Alert:",
}


def retrieve_context(
    question: str,
    lat: float | None = None,
    lng: float | None = None,
    limit: int | None = None,
) -> list[ContextChunk]:
    """Return ranked context chunks for a user question."""
    normalized_question = normalize(question)
    tokens = tokenize(question)
    intent = detect_intent(normalized_question)
    chunks = knowledge_chunks(lat, lng)

    for chunk in chunks:
        chunk.score = score_chunk(chunk, tokens, normalized_question, intent)

    ranked = sorted(
        chunks,
        key=lambda chunk: (
            chunk.score,
            -distance_sort_value(chunk),
        ),
        reverse=True,
    )

    if intent in INTENT_PREFIX:
        selected = filter_intent_chunks(intent, ranked)
        return selected[:limit] if limit else selected

    selected = [
        chunk
        for chunk in ranked
        if chunk.score > 0 and not chunk.title.startswith(("Hospitals:", "Police:", "Road Alert:", "Towing:"))
    ]
    selected = selected[: limit or 5]
    return selected or ranked[: limit or 3]


def score_chunk(
    chunk: ContextChunk,
    tokens: set[str],
    normalized_question: str,
    intent: str,
) -> int:
    title = normalize(chunk.title)
    text = normalize(f"{chunk.title} {chunk.body}")
    score = 0

    for token in tokens:
        if token in text:
            score += weight_for_token(token)
        if token in title:
            score += weight_for_token(token)

    for phrase in important_phrases(normalized_question):
        if phrase in text:
            score += 12
        if phrase in title:
            score += 10

    score += intent_boost(intent, chunk.title)
    if intent in INTENT_PREFIX:
        score += distance_boost(chunk)

    return score


def distance_sort_value(chunk: ContextChunk) -> float:
    if not chunk.metadata:
        return 999999.0
    distance = chunk.metadata.get("distance_km")
    if distance is None:
        return 999999.0
    return float(distance)


def detect_intent(text: str) -> str:
    """Classify common RoadSoS chat requests."""
    if "police" in text or "cop" in text:
        return "police"
    if any(word in text for word in ["tow", "towing", "recovery", "breakdown", "mechanic"]):
        return "towing"
    if any(word in text for word in ["hospital", "ambulance", "doctor", "medical", "clinic"]):
        return "hospital"
    if "alert" in text or "traffic" in text or "jam" in text or re.search(r"\bnh\s*\d+\b", text):
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
    prefix = INTENT_PREFIX[intent]
    return [chunk for chunk in chunks if chunk.title.startswith(prefix)]


def distance_boost(chunk: ContextChunk) -> int:
    distance = None
    if chunk.metadata:
        distance = chunk.metadata.get("distance_km")
    if distance is None:
        match = re.search(r"Distance: ([0-9.]+) km", chunk.body)
        if match:
            distance = float(match.group(1))
    if distance is None:
        return 0
    return max(0, int(30 - float(distance)))


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
        "bangalore",
        "hyderabad",
    ]
    return [phrase for phrase in phrases if phrase in text]


def weight_for_token(token: str) -> int:
    emergency_terms = {
        "accident",
        "ambulance",
        "bleeding",
        "brake",
        "breakdown",
        "burn",
        "crash",
        "emergency",
        "fire",
        "fracture",
        "hospital",
        "police",
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
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    sections = re.split(r"\n(?=GUIDE \d+:|=== SECTION \d+:)", text)
    chunks: list[ContextChunk] = []
    for section in sections:
        clean = "\n".join(line.strip() for line in section.splitlines() if line.strip())
        if len(clean) < 80:
            continue
        chunks.append(
            ContextChunk(
                title=clean.splitlines()[0][:90],
                body=clean[:5000],
                metadata={"source": filename},
            )
        )
    return chunks


def load_text_path(filename: str) -> Path:
    return DATA_DIR / filename


def alert_chunks(lat: float | None = None, lng: float | None = None) -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    for alert in load_json("road_alerts.json"):
        location = alert.get("location") or {}
        distance = None
        distance_text = ""
        if lat is not None and lng is not None and location.get("lat") is not None and location.get("lng") is not None:
            distance = distance_km(lat, lng, float(location["lat"]), float(location["lng"]))
            distance_text = f" Distance: {distance} km."

        body = (
            f"{alert.get('title', 'Road alert')}. Severity: {alert.get('severity', 'unknown')}. "
            f"Status: {alert.get('status', 'unknown')}. Road: {alert.get('road', 'unknown')}, "
            f"{alert.get('direction', 'direction unknown')}. Location: {location.get('address', 'unknown')}. "
            f"{distance_text} Details: {alert.get('description', '')} "
            f"Detour: {alert.get('detour') or 'No detour listed'}."
        )
        chunks.append(
            ContextChunk(
                title=f"Road Alert: {alert.get('title', 'Road alert')}",
                body=body,
                metadata={
                    "source": "road_alerts.json",
                    "id": alert.get("id"),
                    "distance_km": distance,
                    "status": alert.get("status"),
                },
            )
        )
    return chunks


def place_chunks(
    title: str,
    filename: str,
    lat: float | None = None,
    lng: float | None = None,
) -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    for place in with_distance(load_json(filename), lat, lng):
        phone = place.get("emergency_phone") or place.get("phone") or "not listed"
        city = place.get("city") or place.get("district") or "nearby area"
        state = place.get("state") or "unknown state"
        distance = place.get("distance_km")
        distance_text = f" Distance: {distance} km." if distance is not None else ""
        address = place.get("address") or "Address not listed"

        body = (
            f"{place.get('name', title)} in {city}, {state}. "
            f"Address: {address}. Phone: {phone}. "
            f"Open 24x7: {place.get('open_24x7', 'unknown')}.{distance_text}"
        )
        if place.get("specialties"):
            body += f" Specialties: {', '.join(map(str, place['specialties']))}."
        if place.get("jurisdiction"):
            body += f" Jurisdiction: {place['jurisdiction']}."
        if place.get("services"):
            body += f" Services: {', '.join(map(str, place['services']))}."

        chunks.append(
            ContextChunk(
                title=f"{title}: {place.get('name', title)}",
                body=body,
                metadata={
                    "source": filename,
                    "id": place.get("id"),
                    "distance_km": distance,
                    "lat": place.get("lat"),
                    "lng": place.get("lng"),
                },
            )
        )
    return chunks


def requested_limit(question: str, default: int = 4) -> int:
    normalized = normalize(question)
    if any(word in normalized.split() for word in ["all", "every", "full"]):
        return 50

    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b(?:any|top|show|give|list)?\s*{word}\b", normalized):
            return value

    match = re.search(
        r"\btop\s+(\d+)\b|\b(\d+)\s+(?:nearby\s+)?(?:hospitals?|police|towing|tow|alerts?)\b",
        normalized,
    )
    if not match:
        return default

    value = int(match.group(1) or match.group(2))
    return max(1, min(value, 50))
