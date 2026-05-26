"""
rule_engine.py - deterministic emergency action rules.

This module gives RoadSoS a fast, offline-safe way to classify common road
emergencies and return ordered actions before any LLM/RAG step is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmergencyRule:
    intent: str
    title: str
    severity: str
    keywords: tuple[str, ...]
    emergency_numbers: tuple[str, ...]
    actions: tuple[str, ...]
    avoid: tuple[str, ...] = ()
    priority: int = 0


@dataclass
class RuleMatch:
    intent: str
    title: str
    severity: str
    score: int
    emergency_numbers: list[str]
    actions: list[str]
    avoid: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "title": self.title,
            "severity": self.severity,
            "score": self.score,
            "emergency_numbers": self.emergency_numbers,
            "actions": self.actions,
            "avoid": self.avoid,
            "matched_keywords": self.matched_keywords,
        }


EMERGENCY_RULES: tuple[EmergencyRule, ...] = (
    EmergencyRule(
        intent="crash",
        title="Road accident or crash",
        severity="critical",
        keywords=("accident", "crash", "collision", "hit", "injured", "unconscious", "road accident"),
        emergency_numbers=("112", "108"),
        priority=100,
        actions=(
            "Move yourself to a safe place and switch on hazard lights if possible.",
            "Call 112 or 108 and share the exact location, landmark, road name, and number of injured people.",
            "Check danger first: traffic, leaking fuel, fire, unstable vehicle, or fallen electrical wires.",
            "If the person is unresponsive, check breathing and start CPR only if trained or guided by emergency services.",
            "Keep the injured person warm and still until help arrives.",
        ),
        avoid=(
            "Do not move a victim if spine, neck, or head injury is suspected unless there is immediate danger.",
            "Do not remove a motorcyclist's helmet unless the airway is blocked.",
            "Do not give food or water to an unconscious or semi-conscious person.",
        ),
    ),
    EmergencyRule(
        intent="bleeding",
        title="Severe bleeding",
        severity="critical",
        keywords=("bleeding", "blood", "severe bleeding", "heavy bleeding", "cut", "wound"),
        emergency_numbers=("108", "112"),
        priority=95,
        actions=(
            "Call 108 immediately for ambulance support.",
            "Apply firm direct pressure with a clean cloth or bandage.",
            "If cloth soaks through, add more material on top and keep pressing.",
            "If bleeding is from a limb and life-threatening, use a tourniquet 5 to 8 cm above the wound and note the time.",
            "Keep the person lying down, warm, and calm.",
        ),
        avoid=(
            "Do not remove an embedded object from the wound.",
            "Do not place a tourniquet on the neck, chest, or abdomen.",
        ),
    ),
    EmergencyRule(
        intent="fire",
        title="Vehicle fire or burn injury",
        severity="critical",
        keywords=("fire", "burn", "smoke", "flames", "vehicle fire", "fuel leak", "petrol leak"),
        emergency_numbers=("101", "108", "112"),
        priority=95,
        actions=(
            "Move away from the vehicle and warn others to keep distance.",
            "Call 101 for fire service and 108 for ambulance if anyone is hurt.",
            "If clothing is burning, smother flames with a blanket or roll the person on the ground.",
            "Cool burns with clean cool running water for at least 20 minutes.",
            "Cover the burn with clean non-fluffy material.",
        ),
        avoid=(
            "Do not use ice, butter, toothpaste, or home remedies on burns.",
            "Do not remove clothing stuck to burned skin.",
            "Do not break blisters.",
        ),
    ),
    EmergencyRule(
        intent="head_injury",
        title="Head, neck, or spine injury",
        severity="critical",
        keywords=("head injury", "concussion", "neck injury", "spine", "spinal", "vomiting", "unconscious"),
        emergency_numbers=("108", "112"),
        priority=90,
        actions=(
            "Call 108 and report a possible head, neck, or spine injury.",
            "Keep the person still and support the head and neck in the position found.",
            "Watch breathing, alertness, vomiting, confusion, and bleeding from nose or ears.",
            "If vomiting occurs, log-roll the person only with help while keeping the spine aligned.",
        ),
        avoid=(
            "Do not twist, bend, or lift the head or neck.",
            "Do not give aspirin or ibuprofen after a head injury.",
        ),
    ),
    EmergencyRule(
        intent="breakdown",
        title="Vehicle breakdown",
        severity="high",
        keywords=("breakdown", "stuck", "engine stopped", "flat tyre", "puncture", "towing", "tow"),
        emergency_numbers=("112", "1033"),
        priority=70,
        actions=(
            "Pull fully off the road if the vehicle can move safely.",
            "Switch on hazard lights and keep passengers away from traffic.",
            "Place the warning triangle behind the vehicle when safe to do so.",
            "Call roadside assistance or 1033 on national highways.",
            "Call 112 immediately if the vehicle is blocking traffic or you feel unsafe.",
        ),
        avoid=(
            "Do not stand behind or beside the vehicle in active traffic.",
            "Do not repair a tyre on the traffic-facing side of the road.",
        ),
    ),
    EmergencyRule(
        intent="tyre_burst",
        title="Tyre burst while driving",
        severity="high",
        keywords=("tyre burst", "tire burst", "burst tyre", "burst tire", "blowout"),
        emergency_numbers=("112", "1033"),
        priority=80,
        actions=(
            "Hold the steering wheel firmly with both hands.",
            "Do not brake suddenly; let the vehicle slow gradually.",
            "Gently steer toward the shoulder once stable.",
            "Switch on hazard lights and stop fully off the road.",
            "Call roadside assistance or 1033 on national highways.",
        ),
        avoid=("Do not slam the brakes or make sharp steering movements.",),
    ),
    EmergencyRule(
        intent="waterlogging",
        title="Flooded or waterlogged road",
        severity="high",
        keywords=("waterlogged", "flood", "flooded", "drowning", "submerged", "water logging"),
        emergency_numbers=("112", "108"),
        priority=75,
        actions=(
            "Do not drive into standing or fast-moving water.",
            "Turn around and use a safer route if possible.",
            "If someone is submerged, call 112 and use a rope, cloth, branch, or flotation aid from a safe position.",
            "Once rescued, check breathing and start CPR if needed and trained.",
            "Take the person to a hospital even if they appear to recover.",
        ),
        avoid=("Do not enter deep or fast-moving water yourself.",),
    ),
    EmergencyRule(
        intent="medical",
        title="Medical emergency on road",
        severity="critical",
        keywords=("ambulance", "heart attack", "chest pain", "breathing", "fainted", "seizure", "medical"),
        emergency_numbers=("108", "112"),
        priority=85,
        actions=(
            "Call 108 and describe symptoms, age if known, and exact location.",
            "Keep the person in a safe place away from traffic.",
            "Monitor breathing and consciousness until help arrives.",
            "If the person is not breathing normally, begin CPR if trained or follow dispatcher instructions.",
        ),
        avoid=("Do not give food, water, or medicine unless advised by medical professionals.",),
    ),
)


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
WORD_RE = re.compile(r"[a-z0-9]+")


def evaluate_emergency(text: str, include_all_matches: bool = False) -> dict[str, Any]:
    """
    Classify a free-text emergency report and return the best action plan.

    Args:
        text: User report, SOS note, or chat message.
        include_all_matches: Include secondary matched rules for debugging/UI.
    """
    normalized = normalize(text)
    matches = sorted(
        (match_rule(rule, normalized) for rule in EMERGENCY_RULES),
        key=lambda item: (item.score, SEVERITY_RANK[item.severity], item.intent),
        reverse=True,
    )
    matches = [match for match in matches if match.score > 0]

    if not matches:
        fallback = fallback_match()
        response = {
            "detected": False,
            "primary": fallback.as_dict(),
            "summary": format_summary(fallback),
        }
        if include_all_matches:
            response["matches"] = []
        return response

    primary = matches[0]
    response = {
        "detected": True,
        "primary": primary.as_dict(),
        "summary": format_summary(primary),
    }
    if include_all_matches:
        response["matches"] = [match.as_dict() for match in matches]
    return response


def get_action_plan(text: str) -> list[str]:
    """Return ordered emergency actions for the best matching rule."""
    result = evaluate_emergency(text)
    return result["primary"]["actions"]


def requires_immediate_help(text: str) -> bool:
    """Return True when the best matching rule should trigger urgent escalation."""
    result = evaluate_emergency(text)
    if not result["detected"]:
        return False
    return result["primary"]["severity"] in {"critical", "high"}


def match_rule(rule: EmergencyRule, normalized_text: str) -> RuleMatch:
    matched_keywords = [keyword for keyword in rule.keywords if phrase_in_text(keyword, normalized_text)]
    score = rule.priority + (len(matched_keywords) * 10) if matched_keywords else 0
    return RuleMatch(
        intent=rule.intent,
        title=rule.title,
        severity=rule.severity,
        score=score,
        emergency_numbers=list(rule.emergency_numbers),
        actions=list(rule.actions),
        avoid=list(rule.avoid),
        matched_keywords=matched_keywords,
    )


def fallback_match() -> RuleMatch:
    return RuleMatch(
        intent="general_sos",
        title="General road emergency",
        severity="high",
        score=0,
        emergency_numbers=["112", "108"],
        actions=[
            "Move to a safe place away from traffic if you can.",
            "Call 112 for immediate emergency help or 108 for ambulance support.",
            "Share your exact location, landmark, road name, and what happened.",
            "Keep your phone reachable and stay visible to responders.",
        ],
        avoid=[
            "Do not put yourself in traffic or other danger while helping.",
        ],
    )


def format_summary(match: RuleMatch) -> str:
    numbers = "/".join(match.emergency_numbers)
    first_action = match.actions[0] if match.actions else "Move to safety and call emergency services."
    return f"{match.title}: call {numbers}. {first_action}"


def normalize(text: str) -> str:
    return " ".join(WORD_RE.findall((text or "").lower()))


def phrase_in_text(phrase: str, normalized_text: str) -> bool:
    normalized_phrase = normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"\b{re.escape(normalized_phrase)}\b", normalized_text) is not None
