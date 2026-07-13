from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.memory import ConversationTurn, expand_followup_question


WORD_RE = re.compile(r"[a-z0-9]+")

EMERGENCY_KEYWORDS = {
    "accident",
    "ambulance",
    "bleeding",
    "blood",
    "crash",
    "emergency",
    "fire",
    "harassment",
    "emergency help",
    "help me now",
    "kidnap",
    "need help",
    "please help",
    "road rage",
    "sos",
    "unsafe",
    "urgent help",
}

ROAD_SAFETY_TERMS = {
    "helmet",
    "licence",
    "license",
    "seatbelt",
    "speed",
    "speeding",
    "traffic",
    "rule",
    "rules",
    "safety",
    "safe",
    "driving",
    "first",
    "aid",
    "cpr",
}

FAQ_TERMS = {"faq", "question", "questions", "how", "what", "why"}

GREETING_TEXTS = {"hi", "hello", "hey", "hai", "hii", "yo", "good morning", "good evening"}
THANKS_TEXTS = {"thanks", "thank you", "thank you so much", "thx"}
GOODBYE_TEXTS = {"bye", "goodbye", "see you", "see you later"}
CASUAL_TEXTS = {
    "how are you",
    "how r you",
    "how are u",
    "how are you doing",
    "who are you",
    "what can you do",
}

LOCATION_TERMS = {
    "near",
    "nearby",
    "nearest",
    "closest",
    "around",
    "where",
    "location",
    "route",
    "safe route",
    "danger zone",
    "danger zones",
}

SERVICE_OVERRIDE_TERMS = {
    "near",
    "nearby",
    "nearest",
    "closest",
    "hospital",
    "hospitals",
    "ambulance",
    "doctor",
    "medical",
    "clinic",
    "police",
    "cop",
    "station",
    "tow",
    "towing",
    "recovery",
    "mechanic",
    "breakdown",
    "bike shop",
    "dealer",
    "dealership",
    "flat tire",
    "flat tyre",
    "route",
    "routes",
    "road risk",
    "location",
    "where am i",
    "danger zone",
    "danger zones",
    "safe route",
    "alert",
    "alerts",
    "puncture",
    "puncture shop",
    "showroom",
    "showrooms",
    "tire shop",
    "tyre shop",
}


@dataclass(frozen=True)
class QueryProfile:
    raw_question: str
    clean_question: str
    normalized_question: str
    retrieval_query: str
    tokens: set[str] = field(default_factory=set)
    intent: str = "general"
    emergency_detected: bool = False
    emergency_keywords: list[str] = field(default_factory=list)
    location_intent: bool = False
    needs_location_services: bool = False
    greeting: bool = False
    casual_chat: bool = False
    thanks: bool = False
    goodbye: bool = False
    datetime_intent: bool = False
    category: str = "General Chat"

    @property
    def social_only(self) -> bool:
        return self.greeting or self.casual_chat or self.thanks or self.goodbye


def classify_query(question: str, history: list[ConversationTurn] | None = None) -> QueryProfile:
    clean_question = clean_text(question)
    normalized = normalize(clean_question)
    tokens = set(WORD_RE.findall(normalized))
    retrieval_query = expand_followup_question(clean_question, history or [])
    retrieval_normalized = normalize(retrieval_query)
    retrieval_tokens = set(WORD_RE.findall(retrieval_normalized))
    emergency_keywords = matched_emergency_keywords(retrieval_normalized)
    intent = detect_intent(retrieval_normalized, retrieval_tokens)
    category = detect_category(retrieval_normalized, retrieval_tokens, intent, bool(emergency_keywords))
    location_intent = detect_location_intent(retrieval_normalized, intent)
    datetime_intent = detect_datetime_intent(retrieval_normalized)

    return QueryProfile(
        raw_question=question or "",
        clean_question=clean_question,
        normalized_question=normalized,
        retrieval_query=retrieval_query,
        tokens=tokens,
        intent=intent,
        emergency_detected=bool(emergency_keywords),
        emergency_keywords=emergency_keywords,
        location_intent=location_intent,
        needs_location_services=location_intent
        or intent in {"ambulance", "hospital", "police", "towing", "route", "danger_zone", "showroom", "puncture_shop"},
        greeting=normalized in GREETING_TEXTS,
        casual_chat=normalized in CASUAL_TEXTS,
        thanks=normalized in THANKS_TEXTS,
        goodbye=normalized in GOODBYE_TEXTS,
        datetime_intent=datetime_intent,
        category=category,
    )


def detect_intent(text: str, tokens: set[str]) -> str:
    if "ambulance" in tokens or any(
        phrase in text
        for phrase in {
            "need ambulance",
            "nearby ambulance",
            "closest ambulance",
            "emergency ambulance",
            "ambulance near me",
            "find ambulance",
            "call ambulance",
        }
    ):
        return "ambulance"
    if tokens & {"hospital", "hospitals", "doctor", "medical", "clinic"}:
        return "hospital"
    if tokens & {"showroom", "showrooms", "dealer", "dealership"} or "bike shop" in text:
        return "showroom"
    if tokens & {"puncture", "tyre", "tire"} or "puncture shop" in text:
        return "puncture_shop"
    if any(term in text for term in {"safe route", "safest route"}) or "route" in tokens:
        return "route"
    if "danger zone" in text or "danger zones" in text or "road risk" in text or "blackspot" in tokens:
        return "danger_zone"
    if "police" in tokens or "cop" in tokens:
        return "police"
    if tokens & {"tow", "towing", "recovery", "breakdown", "mechanic"}:
        return "towing"
    if tokens & {"alert", "alerts", "traffic", "jam"} or re.search(r"\bnh\s*\d+\b", text):
        return "alert"
    if tokens & ROAD_SAFETY_TERMS:
        return "road_safety"
    if "faq" in tokens or "frequently asked" in text:
        return "faq"
    if text in GREETING_TEXTS:
        return "greeting"
    if text in THANKS_TEXTS:
        return "thanks"
    if text in GOODBYE_TEXTS:
        return "goodbye"
    return "general"


def detect_category(text: str, tokens: set[str], intent: str, emergency_detected: bool) -> str:
    if text in GREETING_TEXTS:
        return "Greeting"
    if emergency_detected:
        return "Emergency"
    if intent == "route":
        return "Navigation"
    if intent == "ambulance":
        return "Ambulance"
    if intent == "hospital":
        return "Hospital"
    if intent == "police":
        return "Police"
    if intent == "towing":
        return "Tow"
    if intent == "showroom":
        return "Showroom"
    if intent == "puncture_shop":
        return "Puncture Shop"
    if intent in {"road_safety", "alert", "danger_zone"} or tokens & ROAD_SAFETY_TERMS:
        return "Road Safety"
    if intent == "faq" or tokens & FAQ_TERMS:
        return "FAQ"
    return "General Chat"


def detect_location_intent(text: str, intent: str) -> bool:
    if intent in {"ambulance", "hospital", "police", "towing", "route", "danger_zone", "alert", "showroom", "puncture_shop"}:
        return True
    return any(term in text for term in LOCATION_TERMS)


def detect_datetime_intent(text: str) -> bool:
    tokens = set(text.split())
    if text in {"date", "time", "date time", "current date time"}:
        return True
    if "date" in tokens and tokens & {"today", "todays", "current", "what", "whats"}:
        return True
    if "time" in tokens and tokens & {"current", "what", "whats", "now"}:
        return True
    return False


def matched_emergency_keywords(text: str) -> list[str]:
    return sorted(keyword for keyword in EMERGENCY_KEYWORDS if phrase_in_text(keyword, text))


def phrase_in_text(phrase: str, text: str) -> bool:
    normalized_phrase = normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"\b{re.escape(normalized_phrase)}\b", text) is not None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
