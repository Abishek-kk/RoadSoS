# danger_zone_service.py — geofencing + risk scoring
from typing import Any, Iterable, Mapping, List, Optional
from datetime import datetime

from app.algorithms import geofencing
from app.ai import risk_scorer


# Re-expose geofencing algorithms & models
Geofence = geofencing.Geofence
GeofenceMatch = geofencing.GeofenceMatch
is_inside_geofence = geofencing.is_inside_geofence
check_geofence = geofencing.check_geofence
check_geofences = geofencing.check_geofences
nearby_geofences = geofencing.nearby_geofences
nearest_geofence = geofencing.nearest_geofence
active_geofence_alerts = geofencing.active_geofence_alerts
geofence_transition = geofencing.geofence_transition
risk_multiplier_for_match = geofencing.risk_multiplier_for_match
normalize_geofence = geofencing.normalize_geofence
load_danger_zones = geofencing.load_danger_zones


# Re-expose AI Risk Scorer functions
RiskFactor = risk_scorer.RiskFactor
RiskAssessment = risk_scorer.RiskAssessment
assess_road_risk = risk_scorer.assess_road_risk
calculate_risk_score = risk_scorer.calculate_risk_score
get_risk_level = risk_scorer.get_risk_level
nearby_active_alerts = risk_scorer.nearby_active_alerts
nearby_danger_zones = risk_scorer.nearby_danger_zones


def get_road_risk_assessment(
    lat: float,
    lng: float,
    speed: float | None = None,
    weather: str | None = None,
    road: str | None = None,
    when: Optional[datetime] = None,
    search_radius_km: float = 25.0,
) -> dict[str, Any]:
    """
    Generate a complete, localized road risk assessment for a user's coordinate.
    Includes deterministic score, list of nearest zones and active alerts, and tips.
    """
    return assess_road_risk(
        lat=lat,
        lng=lng,
        speed=speed,
        weather=weather,
        road=road,
        when=when,
        search_radius_km=search_radius_km,
    )


def get_nearby_danger_roads(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    limit: int = 20,
) -> List[dict[str, Any]]:
    """
    Return dangerous road records within radius_km of a live user location.

    This uses the same alert selection as POST /location, so API previews and
    background notifications agree on which nearby roads are dangerous.
    """
    zones = load_danger_zones()
    alerts = active_geofence_alerts(
        lat,
        lng,
        zones,
        max_total_radius_km=radius_km,
    )
    return alerts[:limit]


def check_danger_zone_entry(
    previous_lat: float,
    previous_lng: float,
    current_lat: float,
    current_lng: float,
    warning_buffer_km: float = 2.0,
) -> List[dict[str, Any]]:
    """
    Check if the user transitioned into any danger zones since their last GPS update.
    Returns details of matched zones and whether the boundary was crossed.
    """
    zones = load_danger_zones()
    transitions = []
    for zone in zones:
        trans = geofence_transition(
            previous_lat=previous_lat,
            previous_lng=previous_lng,
            current_lat=current_lat,
            current_lng=current_lng,
            geofence=zone,
        )
        # We are interested in transitions where the user entered or stayed inside
        if trans["event"] in {"entered", "inside"}:
            transitions.append(trans)
    return transitions
