"""
retrieval.py - lightweight RAG retrieval for RoadSoS.

Builds context chunks from local RoadSoS data and ranks them with
sentence-transformers (all-MiniLM-L6-v2) + FAISS cosine similarity.
Fallback distance and intent boosts are applied on top of semantic scores.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.routes._data import (
    DATA_DIR,
    clean_phone_number,
    distance_km,
    load_json,
    nearest_with_fallback,
    with_distance,
)


@dataclass
class ContextChunk:
    title: str
    body: str
    score: float = 0.0
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

_logger = logging.getLogger("roadsos.retrieval")
_encoder: SentenceTransformer | None = None
_faiss_index: faiss.IndexFlatIP | None = None
_chunks: list[ContextChunk] = []
_semantic_search_available = False


def init_embedding_index() -> None:
    global _encoder, _faiss_index, _chunks, _semantic_search_available
    if _chunks:
        return
    _logger.info("Initializing semantic search index (all-MiniLM-L6-v2)...")

    # Index must be built from knowledge_chunks() as requested.
    # Note: For place/alert chunks, we keep lat/lng as None during indexing.
    # Distance is enriched per-query in retrieve_context() on top of semantic scores.
    chunks: list[ContextChunk] = knowledge_chunks(None, None)
    _chunks = chunks

    if not chunks:
        _logger.warning("No knowledge chunks found for indexing.")
        _faiss_index = faiss.IndexFlatIP(384)
        return

    try:
        _encoder = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        texts = [f"{chunk.title} {chunk.body}" for chunk in chunks]
        embeddings = _encoder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        embeddings = np.ascontiguousarray(embeddings.astype("float32"))

        # With normalize_embeddings=True, inner product == cosine similarity.
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)

        _faiss_index = index
        _semantic_search_available = True
        _logger.info(f"Indexed {index.ntotal} chunks (dim={embeddings.shape[1]}).")
    except Exception as exc:
        _encoder = None
        _faiss_index = None
        _semantic_search_available = False
        _logger.warning(
            "Semantic search unavailable; using local keyword retrieval. Error: %s",
            exc,
        )


def retrieve_context(
    question: str,
    lat: float | None = None,
    lng: float | None = None,
    limit: int | None = None,
) -> list[ContextChunk]:
    normalized_question = normalize(question)
    intent = detect_intent(normalized_question)

    if lat is not None and lng is not None and intent in {"hospital", "police", "towing"}:
        return nearest_service_chunks(intent, lat, lng, limit or requested_limit(question, default=4))

    init_embedding_index()

    if not _chunks:
        return []

    if not _semantic_search_available or _encoder is None or _faiss_index is None or _faiss_index.ntotal == 0:
        return retrieve_context_keyword(question, lat, lng, limit, intent)

    q_emb = _encoder.encode([question], normalize_embeddings=True)
    q_emb = np.ascontiguousarray(q_emb.astype("float32"))

    k = min(len(_chunks), _faiss_index.ntotal)
    scores, indices = _faiss_index.search(q_emb, k=k)

    scored: list[tuple[int, float]] = []
    for rank in range(k):
        idx = int(indices[0][rank])
        score = float(scores[0][rank])
        if 0 <= idx < len(_chunks):
            scored.append((idx, score))
    scored.sort(key=lambda x: (-x[1], distance_sort_value(_chunks[x[0]])))

    DISTANCE_SCALE = 0.01
    ranked: list[ContextChunk] = []
    for idx, semantic_score in scored:
        chunk = _chunks[idx]
        chunk = ContextChunk(
            title=chunk.title,
            body=chunk.body,
            metadata=dict(chunk.metadata or {}),
            score=0.0,
        )
        if chunk.title.startswith(("Hospitals:", "Police:", "Towing:")):
            _enrich_distance(chunk, lat, lng)
        boost = intent_boost(intent, chunk.title)
        if intent in INTENT_PREFIX:
            boost += distance_boost(chunk) * DISTANCE_SCALE
        chunk.score = semantic_score + boost
        ranked.append(chunk)

    if intent in INTENT_PREFIX:
        selected = filter_intent_chunks(intent, ranked)
        return selected[:limit] if limit else selected

    selected = [
        chunk
        for chunk in ranked
        if chunk.score > 0
        and not chunk.title.startswith(("Hospitals:", "Police:", "Road Alert:", "Towing:"))
    ]
    selected = selected[: limit or 5]
    return selected or ranked[: limit or 3]


def nearest_service_chunks(intent: str, lat: float, lng: float, limit: int) -> list[ContextChunk]:
    service_config = {
        "hospital": ("Hospitals", "hospitals.json", 25.0, "108"),
        "police": ("Police", "police_stations.json", 25.0, "100"),
        "towing": ("Towing", "towing.json", 50.0, "112"),
    }
    title, filename, max_km, fallback_phone = service_config[intent]
    rows = nearest_with_fallback(
        load_json(filename),
        lat,
        lng,
        max_km=max_km,
        limit=max(1, min(limit, 20)),
        fallback_limit=max(1, min(limit, 20)),
    )

    chunks: list[ContextChunk] = []
    for row in rows:
        chunks.append(place_row_chunk(title, filename, row, fallback_phone))
    return chunks


def place_row_chunk(
    title: str,
    filename: str,
    place: dict[str, Any],
    fallback_phone: str,
) -> ContextChunk:
    phone = clean_phone_number(
        place.get("emergency_phone") or place.get("phone"),
        fallback_phone,
    )
    city = place.get("city") or place.get("district") or "nearby area"
    state = place.get("state") or "unknown state"
    distance = place.get("distance_km")
    distance_text = f" Distance: {distance} km." if distance is not None else ""
    address = place.get("address") or "Address not listed"

    body = (
        f"{place.get('name', title)} in {city}, {state}. "
        f"Address: {address}. Phone: {phone}."
        f"{distance_text}"
    )
    if place.get("specialties"):
        body += f" Specialties: {', '.join(map(str, place['specialties']))}."
    if place.get("jurisdiction"):
        body += f" Jurisdiction: {place['jurisdiction']}."
    if place.get("services"):
        body += f" Services: {', '.join(map(str, place['services']))}."

    return ContextChunk(
        title=f"{title}: {place.get('name', title)}",
        body=body,
        metadata={
            "source": filename,
            "id": place.get("id"),
            "distance_km": distance,
            "lat": place.get("lat"),
            "lng": place.get("lng"),
        },
        score=100 - float(distance or 0),
    )


def retrieve_context_keyword(
    question: str,
    lat: float | None,
    lng: float | None,
    limit: int | None,
    intent: str,
) -> list[ContextChunk]:
    tokens = tokenize(question)
    phrases = important_phrases(normalize(question))
    ranked: list[ContextChunk] = []

    for base_chunk in _chunks:
        chunk = ContextChunk(
            title=base_chunk.title,
            body=base_chunk.body,
            metadata=dict(base_chunk.metadata or {}),
            score=0.0,
        )
        if chunk.title.startswith(("Hospitals:", "Police:", "Towing:")):
            _enrich_distance(chunk, lat, lng)

        haystack = normalize(f"{chunk.title} {chunk.body}")
        token_score = sum(weight_for_token(token) for token in tokens if token in haystack)
        phrase_score = sum(12 for phrase in phrases if phrase in haystack)
        score = token_score + phrase_score + intent_boost(intent, chunk.title)
        if intent in INTENT_PREFIX:
            score += distance_boost(chunk) * 0.01
        chunk.score = score
        ranked.append(chunk)

    ranked.sort(key=lambda chunk: (-chunk.score, distance_sort_value(chunk)))

    if intent in INTENT_PREFIX:
        selected = filter_intent_chunks(intent, ranked)
        return selected[:limit] if limit else selected

    selected = [
        chunk
        for chunk in ranked
        if chunk.score > 0
        and not chunk.title.startswith(("Hospitals:", "Police:", "Road Alert:", "Towing:"))
    ]
    selected = selected[: limit or 5]
    return selected or ranked[: limit or 3]


def _enrich_distance(chunk: ContextChunk, lat: float | None, lng: float | None) -> None:
    if lat is None or lng is None:
        return
    metadata = chunk.metadata or {}
    chunk_lat = metadata.get("lat")
    chunk_lng = metadata.get("lng")
    if chunk_lat is None or chunk_lng is None:
        return
    try:
        chunk.metadata["distance_km"] = distance_km(lat, lng, float(chunk_lat), float(chunk_lng))
    except Exception:
        pass


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
    """Builds the full offline knowledge-base chunk list.

    NOTE: If lat/lng are provided, distance fields are embedded into the chunks.
    During semantic indexing we call this with (None, None) and then enrich
    distance on top of semantic scores per-query in retrieve_context().
    """

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


def place_chunks_index() -> list[ContextChunk]:
    chunks: list[ContextChunk] = []
    for filename, title in [
        ("hospitals.json", "Hospitals"),
        ("police_stations.json", "Police"),
        ("towing.json", "Towing"),
    ]:
        for place in load_json(filename):
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
