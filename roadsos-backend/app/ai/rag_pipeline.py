"""
rag_pipeline.py - retrieval + context builder for RoadSoS AI.

This module orchestrates the local retrieval layer, deterministic emergency
rules, LLM generation, and offline fallback responses. It is intentionally
dependency-light so chat can keep working without network or LLM access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

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
You are RoadSoS AI, a calm, highly capable road-safety assistant for India.
Behave like a strong ChatGPT-style helper: understand the user's intent, answer
directly, keep a supportive tone, and ask one useful follow-up question when
details are missing.

Safety rules:
- Use the provided RoadSoS context before general knowledge.
- For crash, medical, fire, severe bleeding, or police emergencies, put the
  emergency number first: 112 for emergency help, 108 for ambulance, 101 for fire,
  100 for police, and 1033 for national-highway help.
- Do not invent phone numbers, distances, addresses, official facts, or service
  availability that are not in context.
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


def run_rag_pipeline(
    question: str,
    messages: list[dict[str, str]] | None = None,
    lat: float | None = None,
    lng: float | None = None,
    use_llm: bool = True,
    context_limit: int | None = None,
    skip: int = 0,
    location_name: str | None = None,
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
    if not question:
        return RagResult(
            reply="Tell me what happened, and I will guide you through the safest next steps.",
            context="",
            sources=[],
            used_llm=False,
            intent="general",
        )

    limit_override = requested_limit(question, default=0) or None
    limit = context_limit or limit_override or 12
    chunks = retrieve_context(question, lat, lng, limit=limit)
    context = build_context(chunks)
    intent = detect_intent(normalize(question))
    emergency = evaluate_emergency(question)

    llm_provider = get_llm_provider()
    if use_llm and should_attempt_llm(llm_provider):
        prompt = build_prompt(question, messages, lat=lat, lng=lng, location_name=location_name)
        safety_snapshot = nearby_safety_snapshot(lat, lng)
        llm_client = get_llm_client(llm_provider)
        reply = llm_client.generate_chat_response(
            prompt=prompt,
            context=build_llm_context(
                context,
                emergency,
                location_name=location_name,
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
    )
    return RagResult(
        reply=fallback_reply,
        context=context,
        sources=source_cards(chunks),
        used_llm=False,
        intent=intent,
        emergency=emergency,
    )


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
    safety_snapshot: str = "",
) -> str:
    blocks: list[str] = []
    if location_name:
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
) -> str:
    lower = question.lower()
    intent = detect_intent(normalize(question))

    if emergency and emergency.get("detected") and should_prioritize_rule(intent):
        return build_emergency_reply(emergency, chunks)

    if location_name and is_location_question(question):
        return (
            f"You're near {location_name}. Are you doing okay - is this urgent, "
            "or are you just checking your location?"
        )

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
