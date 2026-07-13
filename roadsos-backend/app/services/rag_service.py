from __future__ import annotations

import logging
import re
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.retrieval import requested_limit
from app.services.context_builder import (
    ContextPackage,
    LiveContext,
    build_context_package,
    build_live_context,
    is_location_question,
    verified_direct_answer,
)
from app.services.emergency_router import EmergencyContext, run_emergency_workflow
from app.services.llm_router import GenerationResult, generate
from app.services.memory import build_conversation_history, format_history
from app.services.prompt_builder import build_prompt
from app.services.query_classifier import QueryProfile, classify_query
from app.services.retriever import RetrievalDocument, retrieve


logger = logging.getLogger("roadsos.ai")
VERIFIED_LOCATION_INTENTS = {"ambulance", "hospital", "police", "towing", "route", "danger_zone"}
PROMPT_HISTORY_LIMIT = 8
DEFAULT_RETRIEVAL_TOP_K = 6
EMERGENCY_RETRIEVAL_TOP_K = 12


@dataclass
class RagSource:
    title: str
    score: float
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
    llm_provider: str = "none"
    retrieval_confidence: float = 0.0
    response_source: str = "direct"

    def as_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "context": self.context,
            "sources": [source.as_dict() for source in self.sources],
            "used_llm": self.used_llm,
            "intent": self.intent,
            "emergency": self.emergency,
            "llm_provider": self.llm_provider,
            "retrieval_confidence": self.retrieval_confidence,
            "response_source": self.response_source,
        }


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
    emergency_contacts: list[dict[str, Any]] | None = None,
    on_token: Callable[[str], None] | None = None,
    db: Session | None = None,
) -> RagResult:
    started = time.perf_counter()
    clean_question = (question or "").strip()
    history = build_conversation_history(messages)
    prompt_history = history[-PROMPT_HISTORY_LIMIT:]
    profile = classify_query(clean_question, history)
    logger.info("Query received: %s", profile.clean_question[:200])
    logger.info(
        "Intent detected: intent=%s category=%s emergency=%s location=%s greeting=%s",
        profile.intent,
        profile.category,
        profile.emergency_detected,
        profile.location_intent,
        profile.greeting,
    )

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
        collect_places=should_collect_nearby_places(profile, nearby_places),
        db=db,
    )

    contact_reply = direct_contact_reply(profile, emergency_contacts or [])
    if contact_reply:
        empty_context = ContextPackage(
            context="",
            retrieved_context="",
            live_context=live_context,
            location_services_block="",
            safety_snapshot_block="",
            confidence=1.0,
            documents=[],
        )
        return finalize(
            reply=contact_reply,
            context_package=empty_context,
            profile=profile,
            emergency_context=EmergencyContext(detected=False),
            used_llm=False,
            llm_provider="none",
            response_source="direct",
            started=started,
        )

    direct_reply = fast_direct_reply(profile, live_context)
    if direct_reply:
        empty_context = ContextPackage(
            context="",
            retrieved_context="",
            live_context=live_context,
            location_services_block="",
            safety_snapshot_block="",
            confidence=0.0,
            documents=[],
        )
        return finalize(
            reply=direct_reply,
            context_package=empty_context,
            profile=profile,
            emergency_context=EmergencyContext(detected=False),
            used_llm=False,
            llm_provider="none",
            # direct deterministic path (greetings, location, datetime)
            response_source="direct",
            started=started,
        )

    default_top_k = EMERGENCY_RETRIEVAL_TOP_K if profile.emergency_detected else DEFAULT_RETRIEVAL_TOP_K
    top_k = context_limit or requested_limit(profile.clean_question, default=default_top_k)
    retrieval_start = time.perf_counter()
    retrieval_result = retrieve(
        profile,
        lat=lat,
        lng=lng,
        top_k=top_k,
        emergency_contacts=emergency_contacts,
    )
    retrieval_elapsed_ms = round((time.perf_counter() - retrieval_start) * 1000, 2)
    logger.info(
        "Documents found: %s; confidence score=%.3f; retrieval_ms=%s",
        len(retrieval_result.documents),
        retrieval_result.confidence,
        retrieval_elapsed_ms,
    )

    emergency_context = run_emergency_workflow(profile, live_context, emergency_contacts or [])
    if emergency_context.documents:
        retrieval_result.documents = merge_documents(
            retrieval_result.documents,
            emergency_context.documents,
        )
        retrieval_result.confidence = max(retrieval_result.confidence, 0.95)

    context_package = build_context_package(
        profile=profile,
        retrieval_result=retrieval_result,
        live_context=live_context,
        emergency_block=emergency_context.block,
        conversation_memory=format_history(prompt_history),
        include_safety_snapshot=should_include_safety_snapshot(profile),
    )

    if not profile.clean_question:
        return finalize(
            reply="Tell me what happened, and I will guide you through the safest next steps.",
            context_package=context_package,
            profile=profile,
            emergency_context=emergency_context,
            used_llm=False,
            llm_provider="none",
            started=started,
        )

    location_missing = location_context_missing(profile, live_context)
    if location_missing:
        return finalize(
            reply=location_missing,
            context_package=context_package,
            profile=profile,
            emergency_context=emergency_context,
            used_llm=False,
            llm_provider="none",
            started=started,
        )

    if not use_llm:
        return finalize(
            reply=offline_reply(profile, context_package, emergency_context, skip=skip),
            context_package=context_package,
            profile=profile,
            emergency_context=emergency_context,
            used_llm=False,
            llm_provider="none",
            started=started,
        )

    if verified_location_data_required_but_missing(profile, context_package, emergency_context):
        return finalize(
            reply="I don't have enough verified information to answer that.",
            context_package=context_package,
            profile=profile,
            emergency_context=emergency_context,
            used_llm=False,
            llm_provider="none",
            started=started,
        )

    if unsupported_general_query(profile, context_package):
        return finalize(
            reply="I don't have enough verified information to answer that.",
            context_package=context_package,
            profile=profile,
            emergency_context=emergency_context,
            used_llm=False,
            llm_provider="none",
            started=started,
        )

    system_prompt, context, user_prompt = build_prompt(profile, context_package, prompt_history)
    generation_start = time.perf_counter()
    generation_kwargs: dict[str, Any] = {
        "prompt": user_prompt,
        "context": context,
        "system_instruction": system_prompt,
    }
    if profile.emergency_detected and callable_accepts_kwarg(generate, "max_output_tokens"):
        generation_kwargs["max_output_tokens"] = 1024
    if on_token:
        generation_kwargs["on_token"] = on_token
    generation = generate(**generation_kwargs)
    generation_elapsed_ms = round((time.perf_counter() - generation_start) * 1000, 2)
    logger.info(
        "LLM generation completed: provider=%s used_llm=%s generation_ms=%s",
        generation.provider,
        generation.used_llm,
        generation_elapsed_ms,
    )

    if generation.used_llm:
        return finalize(
            reply=generation.reply,
            context_package=context_package,
            profile=profile,
            emergency_context=emergency_context,
            used_llm=True,
            llm_provider=generation.provider,
            response_source="llm",
            started=started,
        )

    return finalize(
        reply=llm_failure_reply(profile, context_package, emergency_context, generation),
        context_package=context_package,
        profile=profile,
        emergency_context=emergency_context,
        used_llm=False,
        llm_provider=generation.provider,
        response_source="fallback",
        started=started,
    )


def callable_accepts_kwarg(func: Callable[..., Any], kwarg: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    return kwarg in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def verified_location_data_required_but_missing(
    profile: QueryProfile,
    context_package: ContextPackage,
    emergency_context: EmergencyContext,
) -> bool:
    """Keep hard refusals only for nearby-service asks with no verified data."""
    if profile.emergency_detected:
        return False
    if not requires_verified_location_data(profile):
        return False
    if emergency_context.block or context_package.documents:
        return False
    if context_package.location_services_block and "User coordinates are unavailable" not in context_package.location_services_block:
        return False
    return True


def requires_verified_location_data(profile: QueryProfile) -> bool:
    return not profile.emergency_detected and profile.intent in VERIFIED_LOCATION_INTENTS


def should_collect_nearby_places(
    profile: QueryProfile,
    nearby_places: list[dict[str, Any]] | None,
) -> bool:
    if nearby_places:
        return False
    return profile.emergency_detected or profile.needs_location_services


def should_include_safety_snapshot(profile: QueryProfile) -> bool:
    return profile.emergency_detected or profile.needs_location_services


def direct_contact_reply(profile: QueryProfile, contacts: list[dict[str, Any]]) -> str | None:
    if not contacts:
        return None

    text = profile.normalized_question or ""
    if not looks_like_contact_lookup(text):
        return None

    matches = matching_contacts(text, contacts)
    if not matches and asks_for_all_contacts(text):
        matches = contacts
    if not matches:
        return "I could not find that person in your saved emergency contacts."

    if len(matches) == 1:
        contact = matches[0]
        name = clean_contact_value(contact.get("name")) or "That contact"
        phone = clean_contact_value(contact.get("phone")) or "not listed"
        relation = clean_contact_value(contact.get("relation"))
        relation_text = f" ({relation})" if relation else ""
        return f"{name}{relation_text}'s phone number is {phone}."

    lines = ["Saved emergency contacts:"]
    for contact in matches:
        name = clean_contact_value(contact.get("name")) or "Emergency contact"
        phone = clean_contact_value(contact.get("phone")) or "not listed"
        relation = clean_contact_value(contact.get("relation"))
        relation_text = f" ({relation})" if relation else ""
        lines.append(f"- {name}{relation_text}: {phone}")
    return "\n".join(lines)


def looks_like_contact_lookup(text: str) -> bool:
    if not text:
        return False
    tokens = set(text.split())
    identity_words = {
        "mom",
        "mother",
        "mum",
        "mummy",
        "amma",
        "dad",
        "father",
        "appa",
        "friend",
        "friends",
    }
    explicit_contact_words = {
        "contact",
        "contacts",
        "saved contacts",
        "emergency contacts",
    }
    phone_request_words = {"number", "phone", "mobile", "call", "dial"}
    return bool(tokens & identity_words and tokens & phone_request_words) or any(
        phrase in text for phrase in explicit_contact_words
    )


def asks_for_all_contacts(text: str) -> bool:
    return any(
        phrase in text
        for phrase in {
            "contact",
            "contacts",
            "emergency contact",
            "emergency contacts",
            "saved contact",
            "saved contacts",
        }
    )


def matching_contacts(text: str, contacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_tokens = set(text.split())
    relation_aliases = {
        "mom": {"mom", "mother", "mum", "mummy", "amma"},
        "dad": {"dad", "father", "daddy", "appa"},
        "friend": {"friend", "friends"},
    }
    matches: list[dict[str, Any]] = []
    for contact in contacts:
        name = clean_contact_value(contact.get("name")).lower()
        relation = clean_contact_value(contact.get("relation")).lower()
        haystack_tokens = set(re.sub(r"[^a-z0-9]+", " ", f"{name} {relation}").split())
        if query_tokens & haystack_tokens:
            matches.append(contact)
            continue
        for canonical, aliases in relation_aliases.items():
            if query_tokens & aliases and (canonical in haystack_tokens or haystack_tokens & aliases):
                matches.append(contact)
                break
    return matches


def clean_contact_value(value: Any) -> str:
    return str(value or "").strip()


def fast_direct_reply(profile: QueryProfile, live_context: LiveContext) -> str | None:
    if profile.intent == "ambulance" and profile.needs_location_services:
        return verified_direct_answer(profile, live_context)
    if profile.social_only or profile.datetime_intent or is_location_question(profile):
        return verified_direct_answer(profile, live_context)
    return None


def unsupported_general_query(profile: QueryProfile, context_package: ContextPackage) -> bool:
    if profile.intent != "general":
        return False
    if profile.emergency_detected or profile.social_only or profile.datetime_intent:
        return False
    if context_package.documents:
        return False

    text = profile.normalized_question or ""
    if not text:
        return True

    if looks_obviously_off_topic(profile) and not looks_road_safety_related(profile):
        return True
    return False


def looks_road_safety_related(profile: QueryProfile) -> bool:
    text = profile.normalized_question or ""
    domain_terms = {
        "accident",
        "ambulance",
        "aid",
        "alert",
        "auto",
        "battery",
        "bike",
        "breakdown",
        "bus",
        "car",
        "clinic",
        "cpr",
        "crash",
        "danger",
        "doctor",
        "drive",
        "driver",
        "driving",
        "emergency",
        "first",
        "fog",
        "fuel",
        "help",
        "helmet",
        "highway",
        "hospital",
        "injured",
        "injury",
        "lane",
        "licence",
        "license",
        "mechanic",
        "medical",
        "motorcycle",
        "petrol",
        "police",
        "puncture",
        "rain",
        "rider",
        "road",
        "roadsos",
        "route",
        "safe",
        "safety",
        "scooter",
        "pressure",
        "brake",
        "brakes",
        "oil",
        "inspection",
        "seatbelt",
        "shock",
        "sos",
        "speed",
        "stuck",
        "tow",
        "towing",
        "traffic",
        "trauma",
        "truck",
        "tyre",
        "tire",
        "vehicle",
        "weather",
    }
    domain_phrases = {
        "first aid",
        "hazard lights",
        "road rage",
        "safe route",
        "seat belt",
        "speed limit",
        "tyre pressure",
        "check tyre pressure",
        "check tire pressure",
        "how to check tyre pressure",
        "how to check tire pressure",
        "tire pressure",
        "vehicle stopped",
    }
    if bool(profile.tokens & domain_terms):
        return True
    # match phrases as whole-word fragments to avoid accidental substring matches
    for phrase in domain_phrases:
        try:
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return True
        except re.error:
            if phrase in text:
                return True
    return False


def looks_obviously_off_topic(profile: QueryProfile) -> bool:
    text = profile.normalized_question or ""
    off_topic_phrases = {
        "capital of",
        "cricket score",
        "football score",
        "stock price",
        "stock market",
        "world cup",
        "write code",
    }
    off_topic_tokens = {
        "actor",
        "algebra",
        "bitcoin",
        "cake",
        "calculus",
        "cinema",
        "cook",
        "cooking",
        "crypto",
        "election",
        "fifa",
        "game",
        "ipl",
        "joke",
        "lyrics",
        "movie",
        "pasta",
        "politics",
        "president",
        "programming",
        "quantum",
        "recipe",
        "song",
        "sports",
        "tennis",
    }
    off_topic_requests = {
        "who won",
        "who is winning",
        "recommend a movie",
        "tell me a joke",
        "make me a recipe",
        "write me code",
    }
    return (
        any(phrase in text for phrase in off_topic_phrases)
        or any(phrase in text for phrase in off_topic_requests)
        or bool(profile.tokens & off_topic_tokens)
    )


def finalize(
    reply: str,
    context_package: ContextPackage,
    profile: QueryProfile,
    emergency_context: EmergencyContext,
    used_llm: bool,
    llm_provider: str,
    started: float,
    response_source: str = "direct",
) -> RagResult:
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "Response time: %sms; generation completed=%s provider=%s",
        elapsed_ms,
        used_llm,
        llm_provider,
    )
    return RagResult(
        reply=reply,
        context=context_package.context,
        sources=source_cards(context_package.documents),
        used_llm=used_llm,
        intent=profile.intent,
        emergency=emergency_context.rule_result,
        llm_provider=llm_provider,
        retrieval_confidence=context_package.confidence,
        response_source=response_source,
    )


def location_context_missing(profile: QueryProfile, live_context: LiveContext) -> str:
    if not profile.needs_location_services:
        return ""
    if profile.emergency_detected:
        return ""
    if live_context.has_coordinates() or live_context.nearby_places:
        return ""
    if profile.intent in {"ambulance", "hospital", "police", "towing", "route", "danger_zone"}:
        return (
            "I don't have enough verified information to answer that. "
            "Share or allow your location so I can use verified nearby RoadSoS data."
        )
    return ""


def offline_reply(
    profile: QueryProfile,
    context_package: ContextPackage,
    emergency_context: EmergencyContext,
    skip: int = 0,
) -> str:
    direct = verified_direct_answer(profile, context_package.live_context, emergency_context.block)
    if direct:
        return direct
    if context_package.documents:
        return format_retrieved_documents_reply(context_package.documents, skip=skip)
    if profile.social_only:
        social = verified_direct_answer(profile, context_package.live_context)
        if social:
            return social
    return no_context_fallback_reply(profile)


def llm_failure_reply(
    profile: QueryProfile,
    context_package: ContextPackage,
    emergency_context: EmergencyContext,
    generation: GenerationResult,
) -> str:
    direct = verified_direct_answer(profile, context_package.live_context, emergency_context.block)
    if direct:
        return direct
    if context_package.documents:
        return (
            "I could not get a reliable LLM response right now, but I did find this in RoadSoS records. "
            + format_retrieved_documents_reply(context_package.documents)
        )
    if profile.social_only:
        social = verified_direct_answer(profile, context_package.live_context)
        if social:
            return social
    logger.warning("LLM fallback had no documents. Last LLM error: %s", generation.error[:300])
    return no_context_fallback_reply(profile)


def no_context_fallback_reply(profile: QueryProfile) -> str:
    if requires_verified_location_data(profile):
        return "I don't have enough verified information to answer that."
    return (
        "I could not reach the AI model right now, but I can still help with road-safety basics, "
        "SOS steps, first aid, and nearby-service guidance when location is available. Try again "
        "or ask a more specific safety question."
    )


def format_retrieved_documents_reply(documents: list[RetrievalDocument], skip: int = 0, limit: int = 3) -> str:
    selected = documents[skip : skip + limit] or documents[:limit]
    summaries = []
    for document in selected:
        snippet = summarize(document.content)
        if snippet:
            summaries.append(f"{document.title}: {snippet}")
    if not summaries:
        return "I couldn't find reliable information in my knowledge base."
    return "Here is the RoadSoS context I found: " + " ".join(summaries)


def source_cards(documents: list[RetrievalDocument], limit: int = 8) -> list[RagSource]:
    return [
        RagSource(
            title=document.title,
            score=document.score,
            snippet=summarize(document.content),
            metadata={**document.metadata, "source": document.source},
        )
        for document in documents[:limit]
    ]


def merge_documents(
    documents: list[RetrievalDocument],
    additions: list[RetrievalDocument],
) -> list[RetrievalDocument]:
    seen = {(document.source, document.title) for document in documents}
    merged = list(documents)
    for document in additions:
        key = (document.source, document.title)
        if key in seen:
            continue
        seen.add(key)
        merged.append(document)
    merged.sort(key=lambda document: -document.score)
    return merged


def summarize(text: str, max_chars: int = 360) -> str:
    cleaned = " ".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."
