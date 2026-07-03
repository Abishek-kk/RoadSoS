from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ai import retrieval as legacy_retrieval
from app.routes._data import DATA_DIR, distance_km, load_json
from app.services.query_classifier import QueryProfile


logger = logging.getLogger("roadsos.ai.retriever")
CONFIDENCE_THRESHOLD = 0.25
MAX_CACHE_ITEMS = 128
_RETRIEVAL_CACHE: dict[tuple[Any, ...], "RetrievalResult"] = {}


@dataclass
class RetrievalDocument:
    title: str
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def cache_copy(self) -> "RetrievalDocument":
        return RetrievalDocument(
            title=self.title,
            content=self.content,
            source=self.source,
            score=self.score,
            metadata=dict(self.metadata),
        )


@dataclass
class RetrievalResult:
    documents: list[RetrievalDocument]
    confidence: float
    query: str

    def cache_copy(self) -> "RetrievalResult":
        return RetrievalResult(
            documents=[document.cache_copy() for document in self.documents],
            confidence=self.confidence,
            query=self.query,
        )


def retrieve(
    profile: QueryProfile,
    lat: float | None = None,
    lng: float | None = None,
    top_k: int = 12,
    emergency_contacts: list[dict[str, Any]] | None = None,
) -> RetrievalResult:
    """
    Central retrieval entrypoint for every AI request.

    It reuses the existing RoadSoS vector/keyword index for static knowledge and
    enriches it with dynamic emergency contacts and danger-zone records.
    """
    query = profile.retrieval_query or profile.clean_question
    cache_key = build_cache_key(profile, lat, lng, top_k, emergency_contacts)
    cached = _RETRIEVAL_CACHE.get(cache_key)
    if cached:
        logger.info("Retrieval cache hit for intent=%s", profile.intent)
        return cached.cache_copy()

    logger.info("Retrieval started for intent=%s", profile.intent)
    documents: list[RetrievalDocument] = []
    documents.extend(static_knowledge_documents(query, lat, lng, top_k=max(top_k, 12)))
    if profile.social_only:
        result = RetrievalResult(documents=[], confidence=0.0, query=query)
        remember(cache_key, result)
        logger.info("Retrieval completed: documents=0 confidence=0.000")
        return result.cache_copy()
    documents.extend(danger_zone_documents(profile, lat, lng))
    documents.extend(structured_knowledge_documents(profile))
    documents.extend(emergency_contact_documents(profile, emergency_contacts or []))

    documents = dedupe_documents(documents)
    documents.sort(key=lambda doc: (-doc.score, doc.source, doc.title.lower()))
    selected = documents[:top_k]
    confidence = calculate_confidence(selected)
    if confidence == 0.0:
        selected = []
    result = RetrievalResult(documents=selected, confidence=confidence, query=query)
    remember(cache_key, result)
    logger.info(
        "Retrieval completed: documents=%s confidence=%.3f",
        len(selected),
        confidence,
    )
    return result.cache_copy()


def static_knowledge_documents(
    query: str,
    lat: float | None,
    lng: float | None,
    top_k: int,
) -> list[RetrievalDocument]:
    chunks = legacy_retrieval.retrieve_context(query, lat, lng, limit=top_k)
    documents: list[RetrievalDocument] = []
    for chunk in chunks:
        source = str((chunk.metadata or {}).get("source") or "local_knowledge_base")
        documents.append(
            RetrievalDocument(
                title=chunk.title,
                content=chunk.body,
                source=source,
                score=float(chunk.score or 0.0),
                metadata=dict(chunk.metadata or {}),
            )
        )
    return documents


def danger_zone_documents(
    profile: QueryProfile,
    lat: float | None,
    lng: float | None,
    limit: int = 8,
) -> list[RetrievalDocument]:
    try:
        rows = load_json("danger_zones.json")
    except Exception:
        return []

    documents: list[RetrievalDocument] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metadata = {
            "source": "danger_zones.json",
            "id": row.get("id"),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
            "risk_level": row.get("risk_level"),
        }
        distance = None
        if lat is not None and lng is not None and row.get("lat") is not None and row.get("lng") is not None:
            distance = distance_km(lat, lng, float(row["lat"]), float(row["lng"]))
            metadata["distance_km"] = distance

        content = (
            f"{row.get('name', 'Danger zone')} on {row.get('road', 'unknown road')} "
            f"near {row.get('city', 'unknown area')}, {row.get('state', 'unknown state')}. "
            f"Risk level: {row.get('risk_level', 'unknown')}. "
            f"Risk score: {row.get('risk_score', 'unknown')}. "
            f"Primary causes: {', '.join(map(str, row.get('primary_causes') or []))}. "
            f"Advisory: {row.get('advisory') or 'No advisory listed'}."
        )
        if distance is not None:
            content += f" Distance: {distance} km."

        score = score_text(profile, content)
        if distance is not None:
            score += max(0.0, 45.0 - distance)
        if profile.intent in {"danger_zone", "route", "alert"}:
            score += 30.0
        if score <= 0:
            continue
        documents.append(
            RetrievalDocument(
                title=f"Danger Zone: {row.get('name', row.get('id', 'Known danger zone'))}",
                content=content,
                source="danger_zones.json",
                score=score,
                metadata=metadata,
            )
        )

    documents.sort(key=lambda doc: (-doc.score, doc.metadata.get("distance_km") or 999999.0))
    return documents[:limit]


def structured_knowledge_documents(profile: QueryProfile, limit: int = 6) -> list[RetrievalDocument]:
    documents: list[RetrievalDocument] = []
    for path in structured_candidate_paths():
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        records = raw.get("records") if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            title = str(record.get("title") or record.get("name") or record.get("id") or path.stem)
            content = record_to_text(record)
            score = score_text(profile, f"{title} {content}")
            if score <= 0:
                continue
            documents.append(
                RetrievalDocument(
                    title=f"Knowledge Base: {title}",
                    content=content,
                    source=str(path.relative_to(DATA_DIR)),
                    score=score,
                    metadata={"id": record.get("id"), "record_type": record.get("record_type")},
                )
            )
    documents.sort(key=lambda doc: -doc.score)
    return documents[:limit]


def emergency_contact_documents(
    profile: QueryProfile,
    contacts: list[dict[str, Any]],
) -> list[RetrievalDocument]:
    if not contacts:
        return []
    if not (profile.emergency_detected or profile.tokens & {"contact", "contacts", "call", "family", "relative"}):
        return []

    documents: list[RetrievalDocument] = []
    for contact in contacts[:10]:
        name = str(contact.get("name") or "Emergency contact").strip()
        phone = str(contact.get("phone") or "not listed").strip()
        relation = str(contact.get("relation") or "emergency contact").strip()
        documents.append(
            RetrievalDocument(
                title=f"Emergency Contact: {name}",
                content=f"{name} is saved as {relation}. Phone: {phone}.",
                source="emergency_contacts",
                score=65.0 if profile.emergency_detected else 45.0,
                metadata={"id": contact.get("id"), "relation": relation},
            )
        )
    return documents


def calculate_confidence(documents: list[RetrievalDocument]) -> float:
    if not documents:
        return 0.0
    top_score = max(document.score for document in documents)
    if top_score <= 1.0:
        return max(0.0, min(1.0, top_score))
    if top_score >= 70:
        return 0.95
    if top_score >= 35:
        return 0.82
    if top_score >= 12:
        return 0.58
    if top_score >= 4:
        return 0.34
    return 0.0


def score_text(profile: QueryProfile, text: str) -> float:
    haystack = normalize(text)
    haystack_tokens = set(haystack.split())
    score = 0.0
    for token in profile.tokens:
        if token in haystack_tokens:
            score += 4.0 if token in {"accident", "hospital", "police", "towing", "fire", "bleeding"} else 1.0
    for phrase in profile.emergency_keywords:
        if normalize(phrase) in haystack:
            score += 12.0
    return score


def structured_candidate_paths() -> list[Path]:
    paths = [
        DATA_DIR / "structured" / "knowledge_base.json",
        DATA_DIR / "structured" / "emergency_services.json",
        DATA_DIR / "structured" / "danger_zones.json",
        DATA_DIR / "structured" / "road_alerts.json",
        DATA_DIR / "faqs.json",
        DATA_DIR / "faq.json",
        DATA_DIR / "emergency_guides.json",
    ]
    return [path for path in paths if path.exists()]


def record_to_text(record: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in (
        "title",
        "name",
        "record_type",
        "category",
        "service_type",
        "city",
        "state",
        "address",
        "phone",
        "description",
        "advisory",
        "source_file",
    ):
        value = record.get(key)
        if value:
            pieces.append(f"{key.replace('_', ' ').title()}: {value}")

    items = record.get("items")
    if isinstance(items, list):
        item_text = []
        for item in items[:20]:
            if isinstance(item, dict):
                item_text.append(str(item.get("text") or item.get("question") or item.get("answer") or item))
            else:
                item_text.append(str(item))
        if item_text:
            pieces.append("Items: " + " ".join(item_text))

    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if value:
                pieces.append(f"{key.replace('_', ' ').title()}: {value}")
    return " ".join(pieces)[:5000]


def build_cache_key(
    profile: QueryProfile,
    lat: float | None,
    lng: float | None,
    top_k: int,
    emergency_contacts: list[dict[str, Any]] | None,
) -> tuple[Any, ...]:
    contact_key = tuple(
        (contact.get("id"), contact.get("name"), contact.get("phone"))
        for contact in (emergency_contacts or [])[:10]
    )
    return (
        normalize(profile.retrieval_query or profile.clean_question),
        round(float(lat), 4) if lat is not None else None,
        round(float(lng), 4) if lng is not None else None,
        int(top_k),
        contact_key,
    )


def remember(cache_key: tuple[Any, ...], result: RetrievalResult) -> None:
    if len(_RETRIEVAL_CACHE) >= MAX_CACHE_ITEMS:
        oldest_key = next(iter(_RETRIEVAL_CACHE))
        _RETRIEVAL_CACHE.pop(oldest_key, None)
    _RETRIEVAL_CACHE[cache_key] = result.cache_copy()


def dedupe_documents(documents: list[RetrievalDocument]) -> list[RetrievalDocument]:
    seen: set[tuple[str, str]] = set()
    deduped: list[RetrievalDocument] = []
    for document in documents:
        key = (document.source, normalize(document.title)[:120])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(document)
    return deduped


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
