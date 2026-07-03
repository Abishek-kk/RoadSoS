"""
rag_pipeline.py - retrieval + context builder for RoadSoS AI.

This module orchestrates the local retrieval layer, deterministic emergency
rules, LLM generation, and offline fallback responses. It is intentionally
dependency-light so chat can keep working without network or LLM access.
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.routes._data import clean_phone_number, load_json, with_distance
from app.ai import gemini_client, local_llm_client
from app.ai.retrieval import (
    ContextChunk,
    detect_intent,
    important_phrases,
    nearby_safety_snapshot,
    normalize,
    requested_limit,
    retrieve_context,
    tokenize,
    weight_for_token,
)
from app.ai.rule_engine import evaluate_emergency
from app.config import get_gemini_api_key, get_llm_provider


SYSTEM_INSTRUCTION = """
You are RoadSoS AI, a concise, location-aware road-safety assistant for India.
You may receive a LIVE CONTEXT block containing current date/time, approximate
city/state/country, coordinates, and a nearby_places_json array. Use that live
context whenever it is relevant; do not claim you lack location or time access
when those fields are present.

Safety rules:
- Use the provided RoadSoS context before general knowledge.
- For crash, medical, fire, severe bleeding, or police emergencies, put the
  emergency number first: 112 for emergency help, 108 for ambulance, 101 for fire,
  100 for police, and 1033 for national-highway help.
- Do not invent phone numbers, distances, addresses, official facts, or service
  availability that are not in context.
- For "where am I" or location questions, answer directly from the live city,
  state, country, or coordinates.
- For date/time questions, answer directly from the live current_datetime.
- For nearby-place questions, filter nearby_places_json by category, list name,
  distance, and address, sorted nearest first. If there is no matching place in
  the live nearby data, say so honestly.
- For emergency-sounding queries, surface the nearest hospital and/or police
  station from nearby_places_json first, then give the shortest useful next
  steps.
- If a user asks for nearby services and location is missing, ask them to allow
  location or share a city/landmark.
- When you know the user's approximate location from context, reference it
  naturally when relevant, such as if asked "where am I" or when it helps frame
  an answer. Do not repeat the location in every reply if it is not relevant.
- If a message could plausibly be an emergency but does not clearly say so, such
  as "my car stopped", "I feel dizzy", or vague distress, briefly ask whether it
  is an emergency right now before or alongside your answer. If the message is
  clearly not urgent, answer normally.
- You may be given a short nearby safety info block listing the closest hospital,
  police station, and towing service. Use your judgment: if the user asked about
  one specific thing and the conversation is casual, just answer that. If the
  situation sounds urgent, stressful, or safety-related, briefly mention other
  nearby options too and restate 112 or 108 as appropriate. Do not dump all
  three options into every reply regardless of context.

Response style:
- Prefer short sections with clear bullets.
- Give practical next steps, not generic advice.
- Keep most answers under 220 words unless the user asks for detail.
"""

LIVE_CONTEXT_RADIUS_KM = 25.0
MAX_LIVE_PLACES_PER_CATEGORY = 8


@dataclass
class NearbyPlace:
    name: str
    category: str
    distance_km: float | None
    address: str
    phone: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None

    def as_context_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "distance_km": self.distance_km,
            "address": self.address,
        }


@dataclass
class LiveContext:
    current_datetime: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float = LIVE_CONTEXT_RADIUS_KM
    nearby_places: list[NearbyPlace] = field(default_factory=list)

    def location_label(self) -> str:
        parts = [self.city, self.state, self.country]
        return ", ".join(part.strip() for part in parts if part and part.strip())

    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def places_for_category(self, category: str) -> list[NearbyPlace]:
        return sorted(
            [place for place in self.nearby_places if place.category == category],
            key=lambda place: (
                place.distance_km is None,
                place.distance_km if place.distance_km is not None else float("inf"),
                place.name.lower(),
            ),
        )


@dataclass
class RagSource:
    title: str
    score: int
    snippet: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "score": self.score,
            "snippet": self.snippet,
            "metadata": self.metadata,
        }


@dataclass
class RagResult:
    reply: str
    context: str
    sources: list[RagSource]
    used_llm: bool
    intent: str
    emergency: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "context": self.context,
            "sources": [source.as_dict() for source in self.sources],
            "used_llm": self.used_llm,
            "intent": self.intent,
            "emergency": self.emergency,
        }


def build_live_context(
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
    current_datetime: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    radius_km: float | None = None,
    nearby_places: list[dict[str, Any]] | None = None,
) -> LiveContext:
    """
    Build the per-request live context used by deterministic replies and LLMs.
    Client-provided nearby places win; otherwise local RoadSoS datasets are used.
    """
    radius = radius_km if radius_km and radius_km > 0 else LIVE_CONTEXT_RADIUS_KM
    places = normalize_nearby_places(nearby_places)
    if not places and lat is not None and lng is not None:
        places = collect_nearby_places(lat, lng, radius_km=radius)

    inferred_city, inferred_state, inferred_country = infer_location_parts(
        location_name=location_name,
        city=city,
        state=state,
        country=country,
        places=places,
    )

    return LiveContext(
        current_datetime=current_datetime or current_datetime_text(),
        city=inferred_city,
        state=inferred_state,
        country=inferred_country,
        latitude=lat,
        longitude=lng,
        radius_km=radius,
        nearby_places=places,
    )


def current_datetime_text() -> str:
    return datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p %Z")


def infer_location_parts(
    location_name: str | None,
    city: str | None,
    state: str | None,
    country: str | None,
    places: list[NearbyPlace],
) -> tuple[str | None, str | None, str | None]:
    clean_city = clean_optional(city)
    clean_state = clean_optional(state)
    clean_country = clean_optional(country)

    if location_name:
        parts = [part.strip() for part in location_name.split(",") if part.strip()]
        if parts and not clean_city:
            clean_city = parts[0]
        if len(parts) > 1 and not clean_state:
            clean_state = parts[1]
        if len(parts) > 2 and not clean_country:
            clean_country = parts[2]

    if not clean_state:
        clean_state = next((place.state for place in places if place.state), None)
    if not clean_country:
        clean_country = next((place.country for place in places if place.country), None)

    return clean_city, clean_state, clean_country


def normalize_nearby_places(rows: list[dict[str, Any]] | None) -> list[NearbyPlace]:
    if not rows:
        return []

    places: list[NearbyPlace] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        category = normalize_place_category(row.get("category"))
        name = clean_optional(row.get("name"))
        if not category or not name:
            continue
        places.append(
            NearbyPlace(
                name=name,
                category=category,
                distance_km=parse_float(row.get("distance_km")),
                address=clean_optional(row.get("address")) or "Address not listed",
                phone=clean_optional(row.get("phone")),
                city=clean_optional(row.get("city")),
                state=clean_optional(row.get("state")),
                country=clean_optional(row.get("country")),
            )
        )

    return sorted_places(places)


def collect_nearby_places(
    lat: float,
    lng: float,
    radius_km: float = LIVE_CONTEXT_RADIUS_KM,
) -> list[NearbyPlace]:
    service_config = [
        ("hospital", "hospitals.json", "108"),
        ("police_station", "police_stations.json", "100"),
        ("towing_service", "towing.json", "112"),
    ]
    places: list[NearbyPlace] = []

    for category, filename, fallback_phone in service_config:
        rows = with_distance(load_json(filename), lat, lng, max_km=radius_km)
        for row in rows[:MAX_LIVE_PLACES_PER_CATEGORY]:
            name = clean_optional(row.get("name") or row.get("station_name"))
            if not name:
                continue
            places.append(
                NearbyPlace(
                    name=name,
                    category=category,
                    distance_km=parse_float(row.get("distance_km")),
                    address=clean_optional(row.get("address")) or "Address not listed",
                    phone=clean_phone_number(
                        row.get("emergency_phone") or row.get("phone"),
                        fallback_phone,
                    ),
                    city=clean_optional(row.get("city") or row.get("district")),
                    state=clean_optional(row.get("state")),
                    country=clean_optional(row.get("country")),
                )
            )

    return sorted_places(places)


def sorted_places(places: list[NearbyPlace]) -> list[NearbyPlace]:
    return sorted(
        places,
        key=lambda place: (
            place.distance_km is None,
            place.distance_km if place.distance_km is not None else float("inf"),
            place.category,
            place.name.lower(),
        ),
    )


def normalize_place_category(value: Any) -> str | None:
    normalized = normalize(str(value or ""))
    aliases = {
        "hospital": "hospital",
        "hospitals": "hospital",
        "medical": "hospital",
        "clinic": "hospital",
        "police": "police_station",
        "police station": "police_station",
        "police stations": "police_station",
        "police_station": "police_station",
        "towing": "towing_service",
        "tow": "towing_service",
        "towing service": "towing_service",
        "towing services": "towing_service",
        "towing_service": "towing_service",
        "atm": "atm",
        "atms": "atm",
        "bank": "bank",
        "banks": "bank",
        "restaurant": "restaurant",
        "restaurants": "restaurant",
        "pharmacy": "pharmacy",
        "pharmacies": "pharmacy",
        "fuel": "fuel_station",
        "petrol": "fuel_station",
        "gas": "fuel_station",
        "fuel station": "fuel_station",
        "fuel stations": "fuel_station",
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalized.replace(" ", "_") if normalized else None


def parse_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def format_live_context_block(live_context: LiveContext) -> str:
    coordinates = "not provided"
    if live_context.has_coordinates():
        coordinates = f"{live_context.latitude}, {live_context.longitude}"
    places_json = json.dumps(
        [place.as_context_dict() for place in live_context.nearby_places],
        ensure_ascii=False,
    )
    return (
        "LIVE CONTEXT\n"
        f"Current Date & Time: {live_context.current_datetime}\n"
        f"User's Location: {live_context.location_label() or 'unknown'}\n"
        f"Coordinates: {coordinates}\n"
        f"Nearby Places (within {format_distance(live_context.radius_km)} km): {places_json}"
    )


def run_rag_pipeline(
    question: str,
    messages: list[dict[str, str]] | None = None,
    lat: float | None = None,
    lng: float | None = None,
    use_llm: bool = True,
    context_limit: int | None = None,
    skip: int = 0,
    location_name: str | None = None,
    current_datetime: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    radius_km: float | None = None,
    nearby_places: list[dict[str, Any]] | None = None,
) -> RagResult:
    """
    Generate a RoadSoS chat answer from local retrieval plus an optional LLM.

    Args:
        question: The current user question.
        messages: Optional recent chat history as {"role": ..., "content": ...}.
        lat/lng: Optional user coordinates for nearest services and alerts.
        use_llm: If False, always return the deterministic fallback answer.
        context_limit: Maximum chunks to retrieve. Explicit user limits still win
            when lower-level callers pass them in.
        location_name: Optional human-readable approximate user location.
    """
    question = (question or "").strip()
    live_context = build_live_context(
        lat=lat,
        lng=lng,
        location_name=location_name,
        current_datetime=current_datetime,
        city=city,
        state=state,
        country=country,
        radius_km=radius_km,
        nearby_places=nearby_places,
    )
    if not question:
        return RagResult(
            reply="Tell me what happened, and I will guide you through the safest next steps.",
            context=format_live_context_block(live_context),
            sources=[],
            used_llm=False,
            intent="general",
        )

    limit_override = requested_limit(question, default=0) or None
    intent = detect_intent(normalize(question))
    emergency = evaluate_emergency(question)
    direct_reply = build_direct_live_context_reply(question, live_context, intent, emergency)
    if direct_reply:
        return RagResult(
            reply=direct_reply,
            context=format_live_context_block(live_context),
            sources=[],
            used_llm=False,
            intent=intent,
            emergency=emergency,
        )

    limit = context_limit or limit_override or 12
    chunks = retrieve_context(question, lat, lng, limit=limit)
    context = build_context(chunks)

    llm_provider = get_llm_provider()
    if use_llm and should_attempt_llm(llm_provider):
        prompt = build_prompt(
            question,
            messages,
            lat=lat,
            lng=lng,
            location_name=location_name,
        )
        safety_snapshot = nearby_safety_snapshot(lat, lng)
        llm_client = get_llm_client(llm_provider)
        reply = llm_client.generate_chat_response(
            prompt=prompt,
            context=build_llm_context(
                context,
                emergency,
                location_name=location_name,
                live_context=live_context,
                safety_snapshot=safety_snapshot,
            ),
            system_instruction=SYSTEM_INSTRUCTION,
        )
        if reply and not reply.lower().startswith("error:"):
            return RagResult(
                reply=reply.strip(),
                context=context,
                sources=source_cards(chunks),
                used_llm=True,
                intent=intent,
                emergency=emergency,
            )

    fallback_reply = build_fallback_reply(
        question,
        chunks,
        skip=skip,
        limit_override=limit_override,
        emergency=emergency,
        location_name=location_name,
        live_context=live_context,
    )
    return RagResult(
        reply=fallback_reply,
        context=context,
        sources=source_cards(chunks),
        used_llm=False,
        intent=intent,
        emergency=emergency,
    )


def build_direct_live_context_reply(
    question: str,
    live_context: LiveContext,
    intent: str,
    emergency: dict[str, Any] | None = None,
) -> str | None:
    if emergency and emergency.get("detected") and should_prioritize_rule(intent):
        return build_live_emergency_reply(emergency, live_context)

    if is_location_question(question):
        return build_location_reply(live_context)

    if is_datetime_question(question):
        return build_datetime_reply(question, live_context)

    if is_small_talk_question(question):
        return build_small_talk_reply(question)

    category = requested_place_category(question, intent)
    if category and is_nearby_place_question(question):
        return build_nearby_place_reply(category, question, live_context)

    return None


def build_location_reply(live_context: LiveContext) -> str:
    label = live_context.location_label()
    coordinates = ""
    if live_context.has_coordinates():
        coordinates = f" Coordinates: {live_context.latitude:.5f}, {live_context.longitude:.5f}."

    if label:
        return f"You're near {label}.{coordinates}"
    if live_context.has_coordinates():
        return f"Your current coordinates are {live_context.latitude:.5f}, {live_context.longitude:.5f}."
    return "I could not determine your location from the live context right now."


def build_datetime_reply(question: str, live_context: LiveContext) -> str:
    normalized = normalize(question)
    if "date" in normalized and "time" not in normalized:
        return f"Today's date is {live_context.current_datetime}."
    if "time" in normalized and "date" not in normalized:
        return f"The current time is {live_context.current_datetime}."
    return f"Current date and time: {live_context.current_datetime}."


def build_small_talk_reply(question: str) -> str:
    normalized = normalize(question)
    if normalized in {"how are you", "how r you", "how are u", "how you doing", "how are you doing"}:
        return (
            "I'm doing well and ready to help. If you're on the road, I can help with "
            "nearby hospitals, police stations, towing, alerts, SOS steps, or first aid."
        )
    if normalized in {"thanks", "thank you", "thank you so much", "thx"}:
        return "You're welcome. Stay safe, and tell me if you need nearby help or road-safety guidance."
    if normalized in {"who are you", "what can you do", "help"}:
        return (
            "I'm RoadSoS AI. I can help with road emergencies, nearby hospitals, police stations, "
            "towing services, road alerts, safer routes, SOS steps, and first aid."
        )
    return (
        "I'm here and ready to help with road safety, nearby emergency services, towing, "
        "alerts, SOS steps, or first aid."
    )


def build_nearby_place_reply(
    category: str,
    question: str,
    live_context: LiveContext,
) -> str:
    if not live_context.nearby_places and not live_context.has_coordinates():
        return "I could not fetch nearby places right now. Share or allow your location and I can narrow this down."

    matches = live_context.places_for_category(category)
    label = category_label(category)
    if not matches:
        return (
            f"I do not have any {label} entries within "
            f"{format_distance(live_context.radius_km)} km in the nearby places data right now."
        )

    limit = requested_limit(question, default=1 if "nearest" in normalize(question) else 5)
    selected = matches[:limit]
    intro = f"Nearest {label}:" if len(selected) == 1 else f"Nearest {label}s:"
    return intro + "\n" + "\n".join(format_place_line(place) for place in selected)


def build_live_emergency_reply(
    emergency: dict[str, Any],
    live_context: LiveContext,
) -> str:
    primary = emergency.get("primary") or {}
    numbers = "/".join(primary.get("emergency_numbers", ["112", "108"]))
    title = primary.get("title") or "Emergency"
    lines: list[str] = []

    nearest_hospital = first_place(live_context, "hospital")
    nearest_police = first_place(live_context, "police_station")
    if nearest_hospital:
        lines.append(f"Nearest hospital: {format_place_plain(nearest_hospital)}")
    else:
        lines.append("Nearest hospital: no hospital entry in the nearby places data.")
    if nearest_police:
        lines.append(f"Nearest police station: {format_place_plain(nearest_police)}")
    else:
        lines.append("Nearest police station: no police station entry in the nearby places data.")

    actions = primary.get("actions", [])[:3]
    action_lines = [f"- {action}" for action in actions]
    return (
        "\n".join(lines)
        + f"\n\n{title}: call {numbers} now if anyone is injured or unsafe.\n"
        + "\n".join(action_lines)
    )


def first_place(live_context: LiveContext, category: str) -> NearbyPlace | None:
    places = live_context.places_for_category(category)
    return places[0] if places else None


def requested_place_category(question: str, intent: str) -> str | None:
    if intent == "hospital":
        return "hospital"
    if intent == "police":
        return "police_station"
    if intent == "towing":
        return "towing_service"

    normalized = normalize(question)
    for phrase, category in {
        "hospital": "hospital",
        "hospitals": "hospital",
        "ambulance": "hospital",
        "doctor": "hospital",
        "medical": "hospital",
        "police": "police_station",
        "cop": "police_station",
        "tow": "towing_service",
        "towing": "towing_service",
        "breakdown": "towing_service",
        "atm": "atm",
        "atms": "atm",
        "bank": "bank",
        "banks": "bank",
        "restaurant": "restaurant",
        "restaurants": "restaurant",
        "pharmacy": "pharmacy",
        "pharmacies": "pharmacy",
        "fuel": "fuel_station",
        "petrol": "fuel_station",
        "gas": "fuel_station",
    }.items():
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            return category
    return None


def is_nearby_place_question(question: str) -> bool:
    normalized = normalize(question)
    place_terms = {
        "hospital",
        "hospitals",
        "ambulance",
        "doctor",
        "medical",
        "police",
        "cop",
        "station",
        "stations",
        "tow",
        "towing",
        "breakdown",
        "atm",
        "atms",
        "bank",
        "banks",
        "restaurant",
        "restaurants",
        "pharmacy",
        "pharmacies",
        "fuel",
        "petrol",
        "gas",
    }
    nearby_terms = {
        "near",
        "nearby",
        "nearest",
        "closest",
        "around",
        "find",
        "show",
        "list",
        "top",
    }
    tokens = set(normalized.split())
    return bool(tokens & place_terms) and bool(tokens & nearby_terms)


def is_datetime_question(question: str) -> bool:
    normalized = normalize(question)
    tokens = set(normalized.split())
    if normalized in {"date", "time", "date time", "current date time"}:
        return True
    if "date" in tokens and tokens & {"today", "todays", "current", "what", "whats"}:
        return True
    if "time" in tokens and tokens & {"current", "what", "whats", "now"}:
        return True
    return False


def is_small_talk_question(question: str) -> bool:
    normalized = normalize(question)
    small_talk = {
        "how are you",
        "how r you",
        "how are u",
        "how you doing",
        "how are you doing",
        "thanks",
        "thank you",
        "thank you so much",
        "thx",
        "who are you",
        "what can you do",
        "help",
    }
    return normalized in small_talk


def category_label(category: str) -> str:
    labels = {
        "hospital": "hospital",
        "police_station": "police station",
        "towing_service": "towing service",
        "atm": "ATM",
        "fuel_station": "fuel station",
    }
    return labels.get(category, category.replace("_", " "))


def format_place_line(place: NearbyPlace) -> str:
    return f"- {format_place_plain(place)}"


def format_place_plain(place: NearbyPlace) -> str:
    distance = "distance unknown"
    if place.distance_km is not None:
        distance = f"{format_distance(place.distance_km)} km"
    return f"{place.name} - {distance}, {place.address}"


def format_distance(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def get_llm_client(provider: str | None = None):
    selected_provider = (provider or get_llm_provider()).strip().lower()
    if selected_provider == "ollama":
        return local_llm_client
    return gemini_client


def should_attempt_llm(provider: str | None = None) -> bool:
    selected_provider = (provider or get_llm_provider()).strip().lower()
    if selected_provider == "ollama":
        return True
    return bool(get_gemini_api_key())


def build_context(chunks: list[ContextChunk], max_chars: int = 9000) -> str:
    """Convert ranked chunks into a compact context block for an LLM."""
    parts: list[str] = []
    total = 0

    for index, chunk in enumerate(chunks, start=1):
        body = clean_space(chunk.body)
        block = f"[{index}] {chunk.title}\nScore: {chunk.score}\n{body}"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 300:
                parts.append(block[:remaining].rstrip())
            break
        parts.append(block)
        total += len(block) + 2

    return "\n\n".join(parts)


def build_llm_context(
    context: str,
    emergency: dict[str, Any] | None = None,
    location_name: str | None = None,
    live_context: LiveContext | None = None,
    safety_snapshot: str = "",
) -> str:
    blocks: list[str] = []
    if live_context:
        blocks.append(format_live_context_block(live_context))
    elif location_name:
        blocks.append(f"User's approximate location: {location_name}.")
    if safety_snapshot:
        blocks.append(
            "Always-available nearby safety info (mention if relevant, do not force it):\n"
            f"{safety_snapshot}"
        )

    if emergency and emergency.get("detected"):
        primary = emergency.get("primary") or {}
        actions = "\n".join(f"- {action}" for action in primary.get("actions", []))
        avoid = "\n".join(f"- {item}" for item in primary.get("avoid", []))
        emergency_block = (
            "Emergency rule match\n"
            f"Title: {primary.get('title')}\n"
            f"Severity: {primary.get('severity')}\n"
            f"Emergency numbers: {', '.join(primary.get('emergency_numbers', []))}\n"
            f"Actions:\n{actions}"
        )
        if avoid:
            emergency_block += f"\nAvoid:\n{avoid}"
        blocks.append(emergency_block)

    if context:
        blocks.append(f"Retrieved context\n{context}")

    return "\n\n".join(blocks) if blocks else context


def build_prompt(
    question: str,
    messages: list[dict[str, str]] | None = None,
    lat: float | None = None,
    lng: float | None = None,
    location_name: str | None = None,
) -> str:
    location_details: list[str] = []
    if location_name:
        location_details.append(f"near {location_name}")
    if lat is not None and lng is not None:
        location_details.append(f"lat {lat}, lng {lng}")
    location = f"\nUser location: {'; '.join(location_details)}" if location_details else ""

    if not messages:
        return f"Current user request: {question}{location}"

    recent = [
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in messages[-6:]
        if item.get("content")
    ]
    if not recent:
        return f"Current user request: {question}{location}"
    return "\n".join(recent) + location


def source_cards(chunks: list[ContextChunk], limit: int = 8) -> list[RagSource]:
    sources: list[RagSource] = []
    for chunk in chunks[:limit]:
        sources.append(
            RagSource(
                title=chunk.title,
                score=chunk.score,
                snippet=summarize(chunk.body),
                metadata=chunk.metadata or {},
            )
        )
    return sources


def build_fallback_reply(
    question: str,
    chunks: list[ContextChunk],
    skip: int = 0,
    limit_override: int | None = None,
    emergency: dict[str, Any] | None = None,
    location_name: str | None = None,
    live_context: LiveContext | None = None,
) -> str:
    lower = question.lower()
    intent = detect_intent(normalize(question))

    if emergency and emergency.get("detected") and should_prioritize_rule(intent):
        if live_context:
            return build_live_emergency_reply(emergency, live_context)
        return build_emergency_reply(emergency, chunks)

    if is_location_question(question) and live_context:
        return build_location_reply(live_context)
    if location_name and is_location_question(question):
        return f"You're near {location_name}."

    if not chunks:
        return (
            "I can help with hospitals, police, towing, road alerts, first aid, and SOS steps.\n\n"
            "Tell me what happened, your city or landmark, and whether anyone is injured. "
            "If this is urgent, call 112 now; for an ambulance call 108."
        )

    if intent in {"hospital", "police", "towing", "alert"}:
        return build_listing_reply(intent, chunks, question, skip, limit_override)

    intro = "Here is the safest next move:"
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
        bullets.append(f"- {summarize_relevant(chunk.body, question)}")

    follow_up = "\n\nTell me your location or nearest landmark and I can narrow this down."
    return f"{intro}\n" + "\n".join(bullets) + follow_up


def is_location_question(question: str) -> bool:
    normalized = normalize(question)
    location_questions = {
        "where am i",
        "where am i now",
        "where are we",
        "where are we now",
        "my location",
        "current location",
        "what is my location",
        "which city am i in",
    }
    return normalized in location_questions


def should_prioritize_rule(intent: str) -> bool:
    return intent not in {"hospital", "police", "towing", "alert"}


def build_emergency_reply(emergency: dict[str, Any], chunks: list[ContextChunk]) -> str:
    primary = emergency.get("primary") or {}
    numbers = "/".join(primary.get("emergency_numbers", ["112", "108"]))
    title = primary.get("title") or "Road emergency"
    actions = [f"- {action}" for action in primary.get("actions", [])[:5]]
    avoid = [f"- Avoid: {item}" for item in primary.get("avoid", [])[:2]]

    if chunks:
        actions.append(f"- Relevant guidance: {summarize_relevant(chunks[0].body, title)}")

    return (
        f"{title}: call {numbers} first.\n"
        + "\n".join(actions + avoid)
        + "\n\nIf you can, share your location, number of injured people, and whether there is fire, fuel leak, or traffic danger."
    )


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
        next_step = "Share your exact location or allow GPS if you want me to rank them more tightly."
    elif intent == "police":
        intro = "Here are the most relevant police contacts. For immediate help, call 100 or 112:"
        next_step = "Tell me the incident type and landmark so I can suggest the best contact path."
    elif intent == "towing":
        intro = "Here are the nearest towing services I found. If you are in danger on the road, call 112 first:"
        next_step = "Move away from traffic, turn on hazard lights, and share vehicle type if you need a better match."
    else:
        intro = "Here are the relevant road alerts from the RoadSoS data:"
        next_step = "Share your route or destination and I can focus on the alerts that matter most."

    if not rows:
        return "I could not find a matching record. Tell me your city, highway, or current location and I will narrow it down."

    return intro + "\n" + "\n".join(f"- {row}" for row in rows) + f"\n\nNext: {next_step}"


def format_listing_row(text: str) -> str:
    cleaned = summarize(text)
    distance = re.search(r"Distance: ([0-9.]+) km", text)
    phone = re.search(r"Phone: ([^.]+)", text)
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


def clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
