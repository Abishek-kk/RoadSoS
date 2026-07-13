from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.retrieval import nearby_safety_snapshot
from app.ai.risk_scorer import nearby_danger_zones
from app.services import ambulance_service
from app.services.hospital_service import HospitalService
from app.services.police_service import PoliceService
from app.services.puncture_shop_service import PunctureShopService
from app.services.query_classifier import QueryProfile, SERVICE_OVERRIDE_TERMS
from app.services.retriever import RetrievalDocument, RetrievalResult
from app.services.showroom_service import ShowroomService
from app.services.towing_service import TowingService


LIVE_CONTEXT_RADIUS_KM = 25.0
MAX_LIVE_PLACES_PER_CATEGORY = 8
_NEARBY_PLACE_CACHE: dict[tuple[float, float, float], list["NearbyPlace"]] = {}
PURE_LOCATION_TERMS = {"location", "where am i"}


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
    lat: float | None = None
    lng: float | None = None
    eta_minutes: int | None = None
    eta: str | None = None
    availability: str | None = None
    officer: str | None = None
    status: str | None = None
    ambulance_id: str | None = None

    def as_context_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "distance_km": self.distance_km,
            "address": self.address,
            "phone": self.phone,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "lat": self.lat,
            "lng": self.lng,
            "eta_minutes": self.eta_minutes,
            "eta": self.eta,
            "availability": self.availability,
            "officer": self.officer,
            "status": self.status,
            "ambulance_id": self.ambulance_id,
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
class ContextPackage:
    context: str
    retrieved_context: str
    live_context: LiveContext
    location_services_block: str
    safety_snapshot_block: str
    confidence: float
    documents: list[RetrievalDocument]


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
    collect_places: bool = True,
    db: Session | None = None,
) -> LiveContext:
    radius = radius_km if radius_km and radius_km > 0 else LIVE_CONTEXT_RADIUS_KM
    places = normalize_nearby_places(nearby_places)
    if collect_places and not places and lat is not None and lng is not None:
        places = collect_nearby_places(lat, lng, radius_km=radius, db=db)

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


def build_context_package(
    profile: QueryProfile,
    retrieval_result: RetrievalResult,
    live_context: LiveContext,
    emergency_block: str = "",
    conversation_memory: str = "",
    include_safety_snapshot: bool = True,
) -> ContextPackage:
    retrieved_context = format_retrieved_context(retrieval_result.documents)
    location_services_block = build_location_services_block(profile, live_context)
    safety_snapshot_block = build_safety_snapshot_block(live_context) if include_safety_snapshot else ""
    blocks = [
        "EMERGENCY CONTEXT" if profile.emergency_detected else "ROADSOS CONTEXT",
        format_live_context_block(live_context),
        location_services_block,
        safety_snapshot_block,
        emergency_block,
        f"RETRIEVED CONTEXT\n{retrieved_context}" if retrieved_context else "",
        f"CONVERSATION MEMORY\n{conversation_memory}" if conversation_memory else "",
    ]
    context = "\n\n".join(block for block in blocks if block.strip())
    confidence = retrieval_result.confidence
    if location_services_block and "User coordinates are unavailable" not in location_services_block:
        confidence = max(confidence, 0.9)
    if emergency_block:
        confidence = max(confidence, 0.95)
    return ContextPackage(
        context=context,
        retrieved_context=retrieved_context,
        live_context=live_context,
        location_services_block=location_services_block,
        safety_snapshot_block=safety_snapshot_block,
        confidence=confidence,
        documents=retrieval_result.documents,
    )


def format_retrieved_context(documents: list[RetrievalDocument], max_chars: int = 4500) -> str:
    parts: list[str] = []
    total = 0
    for index, document in enumerate(documents, start=1):
        body = clean_space(document.content)
        block = (
            f"[{index}] {document.title}\n"
            f"Source: {document.source}\n"
            f"Score: {round(document.score, 3)}\n"
            f"{body}"
        )
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 300:
                parts.append(block[:remaining].rstrip())
            break
        parts.append(block)
        total += len(block) + 2
    return "\n\n".join(parts)


def build_location_services_block(profile: QueryProfile, live_context: LiveContext) -> str:
    if not (profile.needs_location_services or profile.emergency_detected):
        return ""

    if not live_context.has_coordinates() and not live_context.nearby_places:
        return (
            "LOCATION SERVICES\n"
            "User coordinates are unavailable. Do not guess nearest hospitals, police stations, "
            "ambulances, towing services, showrooms, puncture shops, safe routes, or danger zones. "
            "Ask the user to share or allow location."
        )

    lines = ["LOCATION SERVICES"]
    categories = requested_categories(profile)
    for category in categories:
        places = live_context.places_for_category(category)
        if not places:
            lines.append(f"{category_label(category)}: no verified nearby entry in local data.")
            continue
        lines.append(f"{category_label(category)}:")
        for place in places[:3]:
            lines.append(f"- {format_place_plain(place)}")

    if live_context.has_coordinates() and profile.intent in {"danger_zone", "route", "alert"}:
        zones = nearby_danger_zones(live_context.latitude, live_context.longitude, radius_km=live_context.radius_km)
        if zones:
            lines.append("Nearby danger zones:")
            for zone in zones[:5]:
                lines.append(
                    "- "
                    f"{zone.get('name')} ({zone.get('risk_level')} risk, "
                    f"{zone.get('distance_km')} km): {zone.get('advisory') or 'No advisory listed'}"
                )
        else:
            lines.append("Nearby danger zones: none found in local danger-zone data.")

    return "\n".join(lines)


def build_safety_snapshot_block(live_context: LiveContext) -> str:
    if not live_context.has_coordinates():
        return ""
    snapshot = nearby_safety_snapshot(live_context.latitude, live_context.longitude)
    if not snapshot:
        return ""
    return (
        "NEARBY SAFETY INFO\n"
        "Always-available nearby safety info. Mention if relevant, but do not force it:\n"
        f"{snapshot}"
    )


def verified_direct_answer(
    profile: QueryProfile,
    live_context: LiveContext,
    emergency_block: str = "",
) -> str | None:
    """Deterministic answer used only when LLM generation is unavailable/disabled."""
    if is_location_question(profile):
        return build_location_reply(live_context)
    if profile.datetime_intent:
        return build_datetime_reply(profile, live_context)
    if profile.social_only:
        return build_social_reply(profile)
    category = place_category_for_profile(profile)
    if category and profile.needs_location_services:
        return build_nearby_place_reply(category, profile, live_context)
    if profile.emergency_detected and emergency_block:
        return summarize_emergency_block(emergency_block)
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
    return "I don't have enough verified information to answer that. Share or allow your location and I can help."


def build_datetime_reply(profile: QueryProfile, live_context: LiveContext) -> str:
    text = profile.normalized_question
    if "date" in text and "time" not in text:
        return f"Today's date is {live_context.current_datetime}."
    if "time" in text and "date" not in text:
        return f"The current time is {live_context.current_datetime}."
    return f"Current date and time: {live_context.current_datetime}."


def build_social_reply(profile: QueryProfile) -> str:
    if profile.greeting:
        return (
            "Hi, I am RoadSoS AI. I can help with nearby hospitals, police stations, "
            "towing services, road alerts, first aid, SOS steps, and driving safety."
        )
    if profile.thanks:
        return "You're welcome. Stay safe, and tell me if you need nearby help or road-safety guidance."
    if profile.goodbye:
        return "Goodbye. Stay safe on the road."
    if profile.casual_chat and profile.normalized_question in {"how are you", "how r you", "how are u", "how are you doing"}:
        return (
            "I'm doing well and ready to help. If you're on the road, I can help with "
            "nearby hospitals, police stations, towing, alerts, SOS steps, or first aid."
        )
    return (
        "I'm ready to help with road safety, nearby emergency services, towing, "
        "alerts, SOS steps, or first aid."
    )


def build_nearby_place_reply(category: str, profile: QueryProfile, live_context: LiveContext) -> str:
    if not live_context.nearby_places and not live_context.has_coordinates():
        return "I don't have enough verified information to answer that. Share or allow your location and I can narrow this down."
    matches = live_context.places_for_category(category)
    label = category_label(category)
    if not matches:
        if category == "ambulance":
            return "No nearby ambulance is currently available."
        return f"I do not have any {label} entries in my knowledge base for this location."
    selected = matches[:requested_limit(profile.clean_question, default=1 if "nearest" in profile.normalized_question else 5)]
    if category == "ambulance":
        return format_ambulance_reply(selected[:3])
    intro = f"Nearest {label}:" if len(selected) == 1 else f"Nearest {label}s:"
    return intro + "\n" + "\n".join(f"- {format_place_plain(place)}" for place in selected)


def format_ambulance_reply(places: list[NearbyPlace]) -> str:
    if not places:
        return "No nearby ambulance is currently available."
    lines = ["🚑 Nearby Ambulances", ""]
    for index, place in enumerate(places, start=1):
        lines.extend(
            [
                f"{index}.",
                f"Ambulance ID : {place.ambulance_id or place.name}",
                f"Distance : {distance_text(place.distance_km)}",
                f"Status : {(place.status or place.availability or 'available').title()}",
            ]
        )
        if index != len(places):
            lines.append("-------------------------")
    return "\n".join(lines)


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
        f"User Location: {live_context.location_label() or 'unknown'}\n"
        f"Coordinates: {coordinates}\n"
        f"Nearby Places JSON (within {format_distance(live_context.radius_km)} km): {places_json}"
    )


def collect_nearby_places(
    lat: float,
    lng: float,
    radius_km: float = LIVE_CONTEXT_RADIUS_KM,
    db: Session | None = None,
) -> list[NearbyPlace]:
    cache_key = (round(float(lat), 5), round(float(lng), 5), round(float(radius_km or LIVE_CONTEXT_RADIUS_KM), 2))
    if db is None and cache_key in _NEARBY_PLACE_CACHE:
        return list(_NEARBY_PLACE_CACHE[cache_key])

    service_config = [
        ("hospital", HospitalService(), radius_km),
        ("police_station", PoliceService(), radius_km),
        ("towing_service", TowingService(), max(radius_km, 50.0)),
        ("showroom", ShowroomService(), radius_km),
        ("puncture_shop", PunctureShopService(), radius_km),
    ]
    places: list[NearbyPlace] = []
    for category, service, search_radius in service_config:
        rows = service.find_nearest(
            lat,
            lng,
            limit=MAX_LIVE_PLACES_PER_CATEGORY,
            radius_km=search_radius,
        )
        for row in rows:
            name = clean_optional(row.get("name") or row.get("station_name"))
            if not name:
                continue
            places.append(
                NearbyPlace(
                    name=name,
                    category=category,
                    distance_km=parse_float(row.get("distance_km")),
                    address=clean_optional(row.get("address")) or "Address not listed",
                    phone=clean_optional(row.get("phone")),
                    city=clean_optional(row.get("city") or row.get("district")),
                    state=clean_optional(row.get("state")),
                    country=clean_optional(row.get("country")),
                    lat=parse_float(row.get("lat")),
                    lng=parse_float(row.get("lng")),
                    eta_minutes=parse_int(row.get("eta_minutes")),
                    eta=clean_optional(row.get("eta")),
                    availability=clean_optional(row.get("availability")),
                    officer=clean_optional(row.get("officer")),
                )
            )

    if db is not None:
        for row in ambulance_service.find_nearest(db, lat, lng, limit=MAX_LIVE_PLACES_PER_CATEGORY):
            places.append(
                NearbyPlace(
                    name=clean_optional(row.get("name") or row.get("ambulance_id")) or "Ambulance",
                    category="ambulance",
                    distance_km=parse_float(row.get("distance_km")),
                    address=clean_optional(row.get("address")) or "Live GPS location",
                    phone=clean_optional(row.get("phone")),
                    lat=parse_float(row.get("lat")),
                    lng=parse_float(row.get("lng")),
                    eta_minutes=parse_int(row.get("eta_minutes")),
                    eta=clean_optional(row.get("eta")),
                    availability=clean_optional(row.get("availability")),
                    status=clean_optional(row.get("status")),
                    ambulance_id=clean_optional(row.get("ambulance_id") or row.get("id")),
                )
            )

    sorted_places_result = sorted_places(places)
    if db is None:
        _NEARBY_PLACE_CACHE[cache_key] = sorted_places_result
    return list(sorted_places_result)


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
                lat=parse_float(row.get("lat")),
                lng=parse_float(row.get("lng")),
                eta_minutes=parse_int(row.get("eta_minutes")),
                eta=clean_optional(row.get("eta")),
                availability=clean_optional(row.get("availability")),
                officer=clean_optional(row.get("officer")),
                status=clean_optional(row.get("status")),
                ambulance_id=clean_optional(row.get("ambulance_id")),
            )
        )
    return sorted_places(places)


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


def requested_categories(profile: QueryProfile) -> list[str]:
    if profile.emergency_detected:
        return ["ambulance", "hospital", "police_station", "towing_service"]
    category = place_category_for_profile(profile)
    if category:
        return [category]
    return ["hospital", "police_station", "towing_service"]


def place_category_for_intent(intent: str) -> str | None:
    return {
        "hospital": "hospital",
        "ambulance": "ambulance",
        "police": "police_station",
        "towing": "towing_service",
        "showroom": "showroom",
        "puncture_shop": "puncture_shop",
    }.get(intent)


def place_category_for_profile(profile: QueryProfile) -> str | None:
    category = place_category_for_intent(profile.intent)
    if category:
        return category
    text = profile.normalized_question
    aliases = {
        "atm": "atm",
        "atms": "atm",
        "bank": "bank",
        "banks": "bank",
        "pharmacy": "pharmacy",
        "pharmacies": "pharmacy",
        "fuel": "fuel_station",
        "petrol": "fuel_station",
        "gas": "fuel_station",
        "restaurant": "restaurant",
        "restaurants": "restaurant",
    }
    for token, value in aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", text):
            return value
    return None


def is_location_question(profile: QueryProfile) -> bool:
    text = (profile.normalized_question or "").strip()
    if not text:
        return False

    # Guard 1: if the classifier already detected a service/data intent
    # (hospital, police, towing, route, danger_zone, alert, showroom,
    # puncture_shop), this is NEVER
    # a pure location question, even if it contains words like "my location".
    if profile.intent in {"ambulance", "hospital", "police", "towing", "route", "danger_zone", "alert", "showroom", "puncture_shop"}:
        return False

    # Guard 2: if the text contains any service-related word, it's asking
    # for a service, not "where am I" - even if intent classification missed it.
    service_terms = SERVICE_OVERRIDE_TERMS - PURE_LOCATION_TERMS
    tokens = set(text.split())
    if tokens & service_terms or any(term in text for term in service_terms):
        return False

    # Only now check for genuine "where am I" style phrasing:
    if re.search(r"\bwhere\b", text) and re.search(r"\b(am|are|i|we)\b", text):
        return True
    if re.search(r"\b(my|current|my current)\b", text) and re.search(r"\b(location|city|town|village|place)\b", text):
        return True
    if re.search(r"\bwhat\b", text) and re.search(r"\b(location|city|town|village|place)\b", text):
        return True
    if re.search(r"\bwhich\b", text) and re.search(r"\b(city|town|village|place)\b", text):
        return True
    return False


def summarize_emergency_block(block: str) -> str:
    lines = [line for line in block.splitlines() if line and not line.endswith("CONTEXT")]
    nearest = [line for line in lines if line.startswith("Nearest ")]
    emergency_type = next((line.split(": ", 1)[1] for line in lines if line.startswith("Emergency type: ")), "Emergency")
    numbers = next((line.split(": ", 1)[1] for line in lines if line.startswith("Emergency numbers: ")), "112, 108")
    number_text = "/".join(part.strip() for part in numbers.split(",") if part.strip())
    actions_start = lines.index("Safety instructions:") if "Safety instructions:" in lines else -1
    actions = lines[actions_start + 1 : actions_start + 5] if actions_start >= 0 else []
    summary = nearest[:3]
    summary.append(f"{emergency_type}: call {number_text} now if anyone is injured or unsafe.")
    summary.extend(actions)
    return "\n".join(summary[:10])


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
        "ambulance": "ambulance",
        "ambulances": "ambulance",
        "police": "police_station",
        "police station": "police_station",
        "police stations": "police_station",
        "police_station": "police_station",
        "towing": "towing_service",
        "tow": "towing_service",
        "towing service": "towing_service",
        "towing services": "towing_service",
        "towing_service": "towing_service",
        "showroom": "showroom",
        "showrooms": "showroom",
        "dealer": "showroom",
        "dealership": "showroom",
        "bike shop": "showroom",
        "puncture": "puncture_shop",
        "puncture shop": "puncture_shop",
        "puncture shops": "puncture_shop",
        "puncture_shop": "puncture_shop",
        "tyre shop": "puncture_shop",
        "tire shop": "puncture_shop",
        "atm": "atm",
        "atms": "atm",
        "bank": "bank",
        "banks": "bank",
        "pharmacy": "pharmacy",
        "pharmacies": "pharmacy",
        "fuel": "fuel_station",
        "petrol": "fuel_station",
        "gas": "fuel_station",
        "restaurant": "restaurant",
        "restaurants": "restaurant",
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalized.replace(" ", "_") if normalized else None


def category_label(category: str) -> str:
    return {
        "hospital": "hospital",
        "ambulance": "ambulance",
        "police_station": "police station",
        "towing_service": "towing service",
        "showroom": "showroom",
        "puncture_shop": "puncture shop",
        "atm": "ATM",
        "fuel_station": "fuel station",
    }.get(category, category.replace("_", " "))


def format_place_plain(place: NearbyPlace) -> str:
    if place.category == "ambulance":
        name = place.ambulance_id or place.name
        status = f", status {place.status.title()}" if place.status else ""
        eta = f", ETA {place.eta}" if place.eta else ""
        return f"{name} - {distance_text(place.distance_km)}, live GPS location{status}{eta}"
    distance = "distance unknown"
    if place.distance_km is not None:
        distance = f"{format_distance(place.distance_km)} km"
    phone = f", phone {place.phone}" if place.phone else ""
    eta = f", ETA {place.eta}" if place.eta else ""
    availability = f", availability {place.availability}" if place.availability else ""
    officer = f", officer {place.officer}" if place.officer else ""
    return f"{place.name} - {distance}, {place.address}{phone}{eta}{availability}{officer}"


def distance_text(value: float | None) -> str:
    if value is None:
        return "distance unknown"
    return f"{format_distance(value)} km"


def format_distance(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def current_datetime_text() -> str:
    return datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p %Z")


def parse_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def requested_limit(question: str, default: int = 4) -> int:
    from app.ai.retrieval import requested_limit as legacy_requested_limit

    return legacy_requested_limit(question, default=default)
