from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.rule_engine import evaluate_emergency
from app.services.context_builder import LiveContext, format_place_plain
from app.services.query_classifier import QueryProfile
from app.services.retriever import RetrievalDocument


@dataclass
class EmergencyContext:
    detected: bool
    rule_result: dict[str, Any] | None = None
    block: str = ""
    documents: list[RetrievalDocument] = field(default_factory=list)


def run_emergency_workflow(
    profile: QueryProfile,
    live_context: LiveContext,
    emergency_contacts: list[dict[str, Any]] | None = None,
) -> EmergencyContext:
    if not profile.emergency_detected:
        return EmergencyContext(detected=False)

    rule_result = evaluate_emergency(profile.clean_question, include_all_matches=True)
    documents = emergency_documents(rule_result, live_context, emergency_contacts or [])
    block = build_emergency_block(rule_result, live_context, emergency_contacts or []) if rule_result.get("detected") else ""
    return EmergencyContext(
        detected=bool(rule_result.get("detected")),
        rule_result=rule_result,
        block=block,
        documents=documents,
    )


def build_emergency_block(
    rule_result: dict[str, Any],
    live_context: LiveContext,
    emergency_contacts: list[dict[str, Any]],
) -> str:
    primary = rule_result.get("primary") or {}
    lines = ["EMERGENCY WORKFLOW CONTEXT"]
    lines.append(f"Detected: {bool(rule_result.get('detected'))}")
    lines.append(f"Emergency type: {primary.get('title', 'General road emergency')}")
    lines.append(f"Severity: {primary.get('severity', 'high')}")
    lines.append(f"Emergency numbers: {', '.join(primary.get('emergency_numbers') or ['112', '108'])}")

    for label, category in (
        ("Nearest ambulance", "ambulance"),
        ("Nearest hospital", "hospital"),
        ("Nearest police station", "police_station"),
        ("Nearest towing service", "towing_service"),
    ):
        place = first_place(live_context, category)
        if place:
            lines.append(f"{label}: {format_place_plain(place)}")
        elif live_context.has_coordinates():
            lines.append(f"{label}: no verified local entry found.")
        else:
            lines.append(f"{label}: coordinates unavailable; do not guess.")

    if emergency_contacts:
        lines.append("Saved emergency contacts:")
        for contact in emergency_contacts[:5]:
            name = contact.get("name") or "Emergency contact"
            phone = contact.get("phone") or "not listed"
            relation = contact.get("relation") or "contact"
            lines.append(f"- {name} ({relation}): {phone}")
    else:
        lines.append("Saved emergency contacts: none found in local database.")

    actions = primary.get("actions") or []
    if actions:
        lines.append("Safety instructions:")
        for action in actions[:6]:
            lines.append(f"- {action}")

    avoid = primary.get("avoid") or []
    if avoid:
        lines.append("Avoid:")
        for item in avoid[:3]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def emergency_documents(
    rule_result: dict[str, Any],
    live_context: LiveContext,
    emergency_contacts: list[dict[str, Any]],
) -> list[RetrievalDocument]:
    primary = rule_result.get("primary") or {}
    documents: list[RetrievalDocument] = []
    if rule_result.get("detected"):
        documents.append(
            RetrievalDocument(
                title=f"Emergency Rule: {primary.get('title', 'General road emergency')}",
                content=build_rule_document(primary),
                source="rule_engine",
                score=90.0,
                metadata={"severity": primary.get("severity"), "intent": primary.get("intent")},
            )
        )

    for label, category in (
        ("Nearest ambulance", "ambulance"),
        ("Nearest hospital", "hospital"),
        ("Nearest police station", "police_station"),
        ("Nearest towing service", "towing_service"),
    ):
        place = first_place(live_context, category)
        if not place:
            continue
        documents.append(
            RetrievalDocument(
                title=label,
                content=format_place_plain(place),
                source="location_services",
                score=85.0,
                metadata={"category": category, "distance_km": place.distance_km},
            )
        )

    for contact in emergency_contacts[:5]:
        documents.append(
            RetrievalDocument(
                title=f"Saved Emergency Contact: {contact.get('name') or 'Contact'}",
                content=(
                    f"{contact.get('name') or 'Emergency contact'} "
                    f"({contact.get('relation') or 'contact'}): {contact.get('phone') or 'not listed'}"
                ),
                source="emergency_contacts",
                score=80.0,
                metadata={"id": contact.get("id")},
            )
        )
    return documents


def build_rule_document(primary: dict[str, Any]) -> str:
    actions = "; ".join(primary.get("actions") or [])
    avoid = "; ".join(primary.get("avoid") or [])
    return (
        f"{primary.get('title', 'General road emergency')}. "
        f"Severity: {primary.get('severity', 'high')}. "
        f"Numbers: {', '.join(primary.get('emergency_numbers') or ['112', '108'])}. "
        f"Actions: {actions}. Avoid: {avoid}."
    )


def first_place(live_context: LiveContext, category: str):
    places = live_context.places_for_category(category)
    return places[0] if places else None
