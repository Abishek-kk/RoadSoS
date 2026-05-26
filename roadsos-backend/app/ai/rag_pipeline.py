"""
rag_pipeline.py - retrieval + context builder for RoadSoS AI.

This module orchestrates the local retrieval layer, deterministic emergency
rules, Gemini generation, and offline fallback responses. It is intentionally
dependency-light so chat can keep working without network or LLM access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.gemini_client import generate_chat_response
from app.ai.retrieval import (
    ContextChunk,
    detect_intent,
    important_phrases,
    normalize,
    requested_limit,
    retrieve_context,
    tokenize,
    weight_for_token,
)
from app.ai.rule_engine import evaluate_emergency
from app.config import get_gemini_api_key


SYSTEM_INSTRUCTION = """
You are RoadSoS AI, a concise road-safety and emergency assistant for India.
Use the provided context first. Give practical, ordered steps.
For urgent medical, crash, fire, or police situations, tell the user to call 112/108 first.
Do not invent phone numbers, distances, or official facts that are not in context.
Keep the answer under 160 words unless the user asks for detail.
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
) -> RagResult:
    """
    Generate a RoadSoS chat answer from local retrieval plus optional Gemini.

    Args:
        question: The current user question.
        messages: Optional recent chat history as {"role": ..., "content": ...}.
        lat/lng: Optional user coordinates for nearest services and alerts.
        use_llm: If False, always return the deterministic fallback answer.
        context_limit: Maximum chunks to retrieve. Explicit user limits still win
            when lower-level callers pass them in.
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

    if use_llm and get_gemini_api_key():
        prompt = build_prompt(question, messages)
        reply = generate_chat_response(
            prompt=prompt,
            context=build_llm_context(context, emergency),
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

    return RagResult(
        reply=build_fallback_reply(
            question,
            chunks,
            skip=skip,
            limit_override=limit_override,
            emergency=emergency,
        ),
        context=context,
        sources=source_cards(chunks),
        used_llm=False,
        intent=intent,
        emergency=emergency,
    )


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


def build_llm_context(context: str, emergency: dict[str, Any] | None = None) -> str:
    if not emergency or not emergency.get("detected"):
        return context

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
    return f"{emergency_block}\n\nRetrieved context\n{context}"


def build_prompt(question: str, messages: list[dict[str, str]] | None = None) -> str:
    if not messages:
        return question

    recent = [
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in messages[-6:]
        if item.get("content")
    ]
    if not recent:
        return question
    return "\n".join(recent)


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
) -> str:
    lower = question.lower()
    intent = detect_intent(normalize(question))

    if emergency and emergency.get("detected") and should_prioritize_rule(intent):
        return build_emergency_reply(emergency, chunks)

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
        bullets.append(f"- {summarize_relevant(chunk.body, question)}")

    if not bullets:
        bullets.append("- Share what happened, your location, and whether anyone is injured.")

    return f"{intro}\n" + "\n".join(bullets)


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

    return f"{title}: call {numbers} first.\n" + "\n".join(actions + avoid)


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
