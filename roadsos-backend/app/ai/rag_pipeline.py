"""
Compatibility layer for the RoadSoS AI pipeline.

The production chat path now lives in app.services.rag_service. This module
keeps older imports working while preventing the old direct-response paths from
remaining as a second implementation.
"""

from __future__ import annotations

from typing import Any

from app.ai import gemini_client, local_llm_client
from app.ai.retrieval import ContextChunk, normalize
from app.config import get_gemini_api_key, get_llm_provider
from app.services.context_builder import (
    LiveContext,
    NearbyPlace,
    build_live_context,
    format_live_context_block,
)
from app.services.prompt_builder import SYSTEM_PROMPT as SYSTEM_INSTRUCTION
from app.services.rag_service import (
    RagResult,
    RagSource,
    format_retrieved_documents_reply,
    run_rag_pipeline,
    source_cards as _source_cards,
)
from app.services.retriever import RetrievalDocument


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
    parts: list[str] = []
    total = 0
    for index, chunk in enumerate(chunks, start=1):
        block = f"[{index}] {chunk.title}\nScore: {chunk.score}\n{chunk.body}"
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
        blocks.append(
            "Emergency rule match\n"
            f"Title: {primary.get('title')}\n"
            f"Severity: {primary.get('severity')}\n"
            f"Emergency numbers: {', '.join(primary.get('emergency_numbers', []))}\n"
            f"Actions:\n{actions}"
        )
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
    recent = [
        f"{item.get('role', 'user')}: {item.get('content', '')}"
        for item in (messages or [])[-20:]
        if item.get("content")
    ]
    if not recent:
        return f"Current user request: {question}{location}"
    return "\n".join(recent) + location


def source_cards(chunks: list[ContextChunk], limit: int = 8) -> list[RagSource]:
    documents = [
        RetrievalDocument(
            title=chunk.title,
            content=chunk.body,
            source=str((chunk.metadata or {}).get("source") or "local_knowledge_base"),
            score=float(chunk.score or 0.0),
            metadata=dict(chunk.metadata or {}),
        )
        for chunk in chunks[:limit]
    ]
    return _source_cards(documents, limit=limit)


def build_fallback_reply(
    question: str,
    chunks: list[ContextChunk],
    skip: int = 0,
    limit_override: int | None = None,
    emergency: dict[str, Any] | None = None,
    location_name: str | None = None,
    live_context: LiveContext | None = None,
) -> str:
    normalized = normalize(question)
    if normalized in {"where am i", "where am i now", "my location", "current location"}:
        if live_context:
            label = live_context.location_label()
            if label:
                return f"You're near {label}."
            if live_context.has_coordinates():
                return f"Your current coordinates are {live_context.latitude:.5f}, {live_context.longitude:.5f}."
        if location_name:
            return f"You're near {location_name}."

    documents = [
        RetrievalDocument(
            title=chunk.title,
            content=chunk.body,
            source=str((chunk.metadata or {}).get("source") or "local_knowledge_base"),
            score=float(chunk.score or 0.0),
            metadata=dict(chunk.metadata or {}),
        )
        for chunk in chunks
    ]
    if documents:
        return format_retrieved_documents_reply(documents, skip=skip, limit=limit_override or 4)
    return "I don't have enough verified information to answer that."
