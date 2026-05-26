"""
risk_scorer.py - road danger scoring engine.

Scores a user's current road risk from RoadSoS danger-zone and live-alert data.
The scorer is deterministic and works without network or LLM access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.routes._data import distance_km, load_json


@dataclass
class RiskFactor:
    source: str
    title: str
    score: float
    distance_km: float | None = None
    details: str = ""
    advisory: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "score": round(self.score, 1),
            "distance_km": self.distance_km,
            "details": self.details,
            "advisory": self.advisory,
        }


@dataclass
class RiskAssessment:
    score: int
    risk_level: str
    summary: str
    safety_tips: list[str]
    nearest_danger_zones: list[dict[str, Any]] = field(default_factory=list)
    active_alerts: list[dict[str, Any]] = field(default_factory=list)
    factors: list[RiskFactor] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "risk_level": self.risk_level,
            "summary": self.summary,
            "safety_tips": self.safety_tips,
            "nearest_danger_zones": self.nearest_danger_zones,
            "active_alerts": self.active_alerts,
            "factors": [factor.as_dict() for factor in self.factors],
        }


SEVERITY_POINTS = {
    "low": 10,
    "medium": 24,
    "moderate": 24,
    "high": 38,
    "critical": 52,
}

ALERT_TYPE_POINTS = {
    "accident": 16,
    "road_damage": 12,
    "traffic": 8,
    "weather": 10,
    "construction": 7,
    "obstruction": 9,
}

WEATHER_POINTS = {
    "clear": 0,
    "normal": 0,
    "rain": 12,
    "heavy rain": 18,
    "fog": 18,
    "low visibility": 18,
    "waterlogging": 18,
    "storm": 20,
    "snow": 16,
}


def assess_road_risk(
    lat: float,
    lng: float,
    speed: float | None = None,
    weather: str | None = None,
    road: str | None = None,
    when: datetime | None = None,
    search_radius_km: float = 25.0,
) -> dict[str, Any]:
    """
    Return a complete risk assessment for a location.

    Score is 0-100. Nearby danger zones, active road alerts, speed, weather,
    and peak-risk timing all contribute to the final score.
    """
    factors: list[RiskFactor] = []
    danger_zones = nearby_danger_zones(lat, lng, search_radius_km)
    alerts = nearby_active_alerts(lat, lng, search_radius_km)

    factors.extend(score_danger_zone(zone, when) for zone in danger_zones[:5])
    factors.extend(score_alert(alert) for alert in alerts[:5])

    speed_factor = score_speed(speed)
    if speed_factor:
        factors.append(speed_factor)

    weather_factor = score_weather(weather, danger_zones)
    if weather_factor:
        factors.append(weather_factor)

    road_factor = score_road_match(road, danger_zones, alerts)
    if road_factor:
        factors.append(road_factor)

    score = combine_factor_scores(factors)
    risk_level = level_for_score(score)
    summary = build_summary(score, risk_level, factors)
    tips = build_safety_tips(risk_level, factors, danger_zones, alerts, speed, weather)

    return RiskAssessment(
        score=score,
        risk_level=risk_level,
        summary=summary,
        safety_tips=tips,
        nearest_danger_zones=[format_zone(zone) for zone in danger_zones[:5]],
        active_alerts=[format_alert(alert) for alert in alerts[:5]],
        factors=sorted(factors, key=lambda factor: factor.score, reverse=True),
    ).as_dict()


def calculate_risk_score(
    lat: float,
    lng: float,
    speed: float | None = None,
    weather: str | None = None,
    road: str | None = None,
) -> int:
    """Convenience wrapper that returns only the 0-100 score."""
    return assess_road_risk(lat, lng, speed=speed, weather=weather, road=road)["score"]


def get_risk_level(score: int | float) -> str:
    """Convert a numeric score to a risk level."""
    return level_for_score(int(round(score)))


def nearby_danger_zones(lat: float, lng: float, radius_km: float = 25.0) -> list[dict[str, Any]]:
    zones = []
    for zone in load_json("danger_zones.json"):
        distance = distance_km(lat, lng, float(zone["lat"]), float(zone["lng"]))
        zone_radius = float(zone.get("radius_km") or 0)
        if distance <= max(radius_km, zone_radius):
            zones.append({**zone, "distance_km": distance, "inside_zone": distance <= zone_radius})
    return sorted(zones, key=lambda item: item["distance_km"])


def nearby_active_alerts(lat: float, lng: float, radius_km: float = 25.0) -> list[dict[str, Any]]:
    alerts = []
    for alert in load_json("road_alerts.json"):
        if str(alert.get("status", "")).lower() not in {"active", "open", "ongoing"}:
            continue
        location = alert.get("location") or {}
        if location.get("lat") is None or location.get("lng") is None:
            continue
        distance = distance_km(lat, lng, float(location["lat"]), float(location["lng"]))
        if distance <= radius_km:
            alerts.append({**alert, "distance_km": distance})
    return sorted(alerts, key=lambda item: item["distance_km"])


def score_danger_zone(zone: dict[str, Any], when: datetime | None = None) -> RiskFactor:
    distance = float(zone.get("distance_km") or 0)
    radius = max(float(zone.get("radius_km") or 1), 0.1)
    base = float(zone.get("risk_score") or 0) * 6

    if distance <= radius:
        proximity_multiplier = 1.0
    else:
        proximity_multiplier = max(0.15, 1 - ((distance - radius) / 20))

    score = base * proximity_multiplier
    if is_peak_risk_time(zone.get("peak_risk_hours") or [], when):
        score += 8

    history = zone.get("accident_history") or {}
    score += min(float(history.get("fatalities_per_year") or 0) * 0.25, 8)
    score += min(float(history.get("accidents_per_year") or 0) * 0.08, 6)

    causes = ", ".join(zone.get("primary_causes") or [])
    details = f"{zone.get('road', 'Road')} near {zone.get('city', 'unknown area')}"
    if causes:
        details += f"; causes: {causes}"

    return RiskFactor(
        source="danger_zone",
        title=str(zone.get("name") or "Known danger zone"),
        score=min(score, 65),
        distance_km=distance,
        details=details,
        advisory=str(zone.get("advisory") or ""),
    )


def score_alert(alert: dict[str, Any]) -> RiskFactor:
    distance = float(alert.get("distance_km") or 0)
    severity = str(alert.get("severity") or "medium").lower()
    alert_type = str(alert.get("type") or "").lower()

    score = float(SEVERITY_POINTS.get(severity, 20))
    score += ALERT_TYPE_POINTS.get(alert_type, 6)
    score += min(float(alert.get("lanes_blocked") or 0) * 4, 14)
    score += min(float(alert.get("casualties") or 0) * 8, 20)
    score += min(float(alert.get("injuries") or 0) * 2, 16)
    score *= max(0.2, 1 - (distance / 30))

    detour = alert.get("detour")
    advisory = f"Detour: {detour}" if detour else "Slow down and follow local traffic directions."
    return RiskFactor(
        source="active_alert",
        title=str(alert.get("title") or "Active road alert"),
        score=min(score, 70),
        distance_km=distance,
        details=str(alert.get("description") or ""),
        advisory=advisory,
    )


def score_speed(speed: float | None) -> RiskFactor | None:
    if speed is None:
        return None
    speed = max(float(speed), 0.0)
    if speed < 75:
        return None
    if speed < 95:
        score = 8
    elif speed < 115:
        score = 16
    else:
        score = 26
    return RiskFactor(
        source="speed",
        title="High vehicle speed",
        score=score,
        details=f"Reported speed is {round(speed, 1)} km/h.",
        advisory="Reduce speed and increase following distance.",
    )


def score_weather(weather: str | None, zones: list[dict[str, Any]]) -> RiskFactor | None:
    if not weather:
        return None
    normalized = weather.strip().lower()
    score = WEATHER_POINTS.get(normalized, 6)

    sensitive_zones = [
        zone
        for zone in zones[:5]
        if normalized in {str(item).lower() for item in zone.get("weather_sensitivity") or []}
    ]
    if sensitive_zones:
        score += 10

    return RiskFactor(
        source="weather",
        title=f"Weather risk: {weather}",
        score=score,
        details=f"{len(sensitive_zones)} nearby danger zone(s) are sensitive to this weather."
        if sensitive_zones
        else "Weather can reduce road grip and visibility.",
        advisory="Use low beam in poor visibility, avoid sudden braking, and keep extra distance.",
    )


def score_road_match(
    road: str | None,
    zones: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> RiskFactor | None:
    if not road:
        return None
    normalized = road.strip().lower()
    if not normalized:
        return None

    matched_zones = [zone for zone in zones if normalized in str(zone.get("road", "")).lower()]
    matched_alerts = [alert for alert in alerts if normalized in str(alert.get("road", "")).lower()]
    if not matched_zones and not matched_alerts:
        return None

    score = min(8 + len(matched_zones) * 4 + len(matched_alerts) * 6, 24)
    return RiskFactor(
        source="road_match",
        title=f"Known risk on {road}",
        score=score,
        details=f"Matched {len(matched_zones)} danger zone(s) and {len(matched_alerts)} active alert(s).",
        advisory="Follow posted signs and prefer suggested detours where available.",
    )


def combine_factor_scores(factors: list[RiskFactor]) -> int:
    if not factors:
        return 12

    ordered = sorted((max(factor.score, 0) for factor in factors), reverse=True)
    total = ordered[0]
    for index, score in enumerate(ordered[1:], start=1):
        total += score * (0.55 ** index)
    return max(0, min(100, int(round(total))))


def level_for_score(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def build_summary(score: int, risk_level: str, factors: list[RiskFactor]) -> str:
    if not factors:
        return "No nearby RoadSoS danger zone or active alert was found. Continue normal defensive driving."

    top = sorted(factors, key=lambda factor: factor.score, reverse=True)[:2]
    reasons = ", ".join(factor.title for factor in top)
    return f"{risk_level.title()} road risk ({score}/100) based on {reasons}."


def build_safety_tips(
    risk_level: str,
    factors: list[RiskFactor],
    zones: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    speed: float | None,
    weather: str | None,
) -> list[str]:
    tips: list[str] = []

    if risk_level in {"critical", "high"}:
        tips.append("Slow down, increase following distance, and avoid risky overtakes.")
    else:
        tips.append("Maintain lane discipline and keep scanning for hazards.")

    if alerts:
        first_alert = alerts[0]
        detour = first_alert.get("detour")
        if detour:
            tips.append(f"Consider detour: {detour}.")
        else:
            tips.append("Follow police, NHAI, or traffic-control instructions near active alerts.")

    if zones and zones[0].get("advisory"):
        tips.append(str(zones[0]["advisory"]))

    if speed is not None and float(speed) >= 75:
        tips.append("Reduce speed before curves, toll areas, crossings, and congested stretches.")

    if weather:
        tips.append("Use headlights appropriately and avoid sudden braking in poor weather.")

    if any(factor.source == "active_alert" and factor.score >= 45 for factor in factors):
        tips.append("If you are near the incident and in danger, call 112 immediately.")

    return dedupe(tips)[:5]


def is_peak_risk_time(ranges: list[str], when: datetime | None = None) -> bool:
    if not ranges:
        return False
    current = when or datetime.now()
    current_minutes = current.hour * 60 + current.minute

    for value in ranges:
        parsed = parse_time_range(str(value))
        if parsed is None:
            continue
        start, end = parsed
        if start <= end and start <= current_minutes <= end:
            return True
        if start > end and (current_minutes >= start or current_minutes <= end):
            return True
    return False


def parse_time_range(value: str) -> tuple[int, int] | None:
    cleaned = (
        value.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("to", "-")
        .replace(" ", "")
    )
    if "-" not in cleaned:
        return None
    start_raw, end_raw = cleaned.split("-", 1)
    start = parse_time_value(start_raw)
    end = parse_time_value(end_raw)
    if start is None or end is None:
        return None
    return start, end


def parse_time_value(value: str) -> int | None:
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def format_zone(zone: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": zone.get("id"),
        "name": zone.get("name"),
        "road": zone.get("road"),
        "city": zone.get("city"),
        "state": zone.get("state"),
        "risk_level": zone.get("risk_level"),
        "risk_score": zone.get("risk_score"),
        "distance_km": zone.get("distance_km"),
        "inside_zone": zone.get("inside_zone", False),
        "advisory": zone.get("advisory"),
    }


def format_alert(alert: dict[str, Any]) -> dict[str, Any]:
    location = alert.get("location") or {}
    return {
        "id": alert.get("id"),
        "title": alert.get("title"),
        "type": alert.get("type"),
        "severity": alert.get("severity"),
        "status": alert.get("status"),
        "road": alert.get("road"),
        "city": location.get("city"),
        "state": location.get("state"),
        "distance_km": alert.get("distance_km"),
        "message": alert.get("description"),
        "detour": alert.get("detour"),
    }


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
