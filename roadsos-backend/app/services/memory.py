from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


MAX_HISTORY_MESSAGES = 20
FOLLOW_UP_TERMS = {
    "that",
    "this",
    "it",
    "one",
    "previous",
    "above",
    "same",
    "there",
}
FOLLOW_UP_PHRASES = {
    "what about the previous one",
    "what about previous one",
    "what about that",
    "what about it",
    "tell me more",
    "more about that",
    "same one",
    "previous one",
}


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str


def build_conversation_history(messages: list[dict[str, Any]] | None) -> list[ConversationTurn]:
    """Return the last 10 user/assistant exchanges as normalized turns."""
    if not messages:
        return []

    history: list[ConversationTurn] = []
    for item in messages:
        role = str(item.get("role") or "").strip().lower()
        content = clean_text(item.get("content") or "")
        if role not in {"user", "assistant", "system"} or not content:
            continue
        history.append(ConversationTurn(role=role, content=content))
    return history[-MAX_HISTORY_MESSAGES:]


def format_history(history: list[ConversationTurn]) -> str:
    if not history:
        return ""
    return "\n".join(f"{turn.role}: {turn.content}" for turn in history[-MAX_HISTORY_MESSAGES:])


def expand_followup_question(question: str, history: list[ConversationTurn]) -> str:
    """
    Add the previous user request to vague follow-ups so retrieval can resolve
    "what about the previous one?" without relying on model guesswork.
    """
    clean_question = clean_text(question)
    if not clean_question or not is_followup(clean_question):
        return clean_question

    previous_user = previous_user_message(history, exclude=clean_question)
    if not previous_user:
        return clean_question
    return f"{previous_user}\nFollow-up question: {clean_question}"


def is_followup(question: str) -> bool:
    normalized = normalize(question)
    if normalized in FOLLOW_UP_PHRASES:
        return True
    tokens = set(normalized.split())
    return bool(tokens & FOLLOW_UP_TERMS) and len(tokens) <= 8


def previous_user_message(history: list[ConversationTurn], exclude: str = "") -> str:
    normalized_exclude = normalize(exclude)
    for turn in reversed(history):
        if turn.role != "user":
            continue
        if normalized_exclude and normalize(turn.content) == normalized_exclude:
            continue
        return turn.content
    return ""


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
