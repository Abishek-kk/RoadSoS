"""
geofencing.py - radius boundary detection for RoadSoS.

Provides pure helpers for checking whether a GPS point is inside or near
RoadSoS danger zones. The functions accept plain dictionaries from
data/danger_zones.json as well as typed Geofence instances.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Geofence:
    id: str
    name: str
    lat: float
    lng: float
    radius_km: float
    risk_level: str = "unknown"
    risk_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any], fallback_id: str = "") -> "Geofence":
        zone_id = str(item.get("id") or item.get("zone_id") or fallback_id)
        return cls(
            id=zone_id,
            name=str(item.get("name") or zone_id or "Unnamed geofence"),
            lat=float(item["lat"]),
            lng=float(item["lng"]),
            radius_km=max(float(item.get("radius_km") or item.get("radius") or 0), 0.0),
            risk_level=str(item.get("risk_level") or "unknown"),
            risk_score=float(item.get("risk_score") or 0.0),
            metadata=dict(item),
        )


@dataclass
class GeofenceMatch:
    geofence: Geofence
    distance_km: float
    inside: bool
    margin_km: float
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.geofence.metadata,
            "id": self.geofence.id,
            "name": self.geofence.name,
            "lat": self.geofence.lat,
            "lng": self.geofence.lng,
            "radius_km": self.geofence.radius_km,
            "risk_level": self.geofence.risk_level,
            "risk_score": self.geofence.risk_score,
            "distance_km": round(self.distance_km, 3),
            "inside_zone": self.inside,
            "margin_km": round(self.margin_km, 3),
            "geofence_status": self.status,
        }


def haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance between two coordinates in kilometers."""
    lat1 = float(lat1)
    lng1 = float(lng1)
    lat2 = float(lat2)
    lng2 = float(lng2)

    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_inside_geofence(
    lat: float,
    lng: float,
    center_lat: float,
    center_lng: float,
    radius_km: float,
) -> bool:
    """Return True when a point is within a circular geofence."""
    return haversine_distance_km(lat, lng, center_lat, center_lng) <= float(radius_km)


def check_geofence(
    lat: float,
    lng: float,
    geofence: Geofence | Mapping[str, Any],
    warning_buffer_km: float = 2.0,
    max_total_radius_km: float | None = None,
) -> GeofenceMatch:
    """
    Check one geofence and return a rich match object.

    status is one of:
    - inside: point is within the geofence radius
    - nearby: point is outside the radius but within warning_buffer_km
    - outside: point is farther away
    """
    zone = normalize_geofence(geofence)
    distance = haversine_distance_km(lat, lng, zone.lat, zone.lng)
    margin = distance - zone.radius_km
    inside = margin <= 0

    effective_buffer_km = float(warning_buffer_km)
    if max_total_radius_km is not None:
        effective_buffer_km = max(0.0, float(max_total_radius_km) - zone.radius_km)

    if inside:
        status = "inside"
    elif margin <= effective_buffer_km:
        status = "nearby"
    else:
        status = "outside"

    return GeofenceMatch(
        geofence=zone,
        distance_km=distance,
        inside=inside,
        margin_km=margin,
        status=status,
    )


def check_geofences(
    lat: float,
    lng: float,
    geofences: Iterable[Geofence | Mapping[str, Any]],
    warning_buffer_km: float = 2.0,
    include_outside: bool = False,
    max_total_radius_km: float | None = None,
) -> list[GeofenceMatch]:
    """Check many geofences and return matches sorted by distance."""
    matches = [
        check_geofence(
            lat,
            lng,
            geofence,
            warning_buffer_km=warning_buffer_km,
            max_total_radius_km=max_total_radius_km,
        )
        for geofence in geofences
    ]
    if not include_outside:
        matches = [match for match in matches if match.status != "outside"]
    return sorted(matches, key=lambda match: match.distance_km)


def nearby_geofences(
    lat: float,
    lng: float,
    geofences: Iterable[Geofence | Mapping[str, Any]],
    search_radius_km: float = 25.0,
) -> list[dict[str, Any]]:
    """
    Return geofences whose center or boundary is within search_radius_km.

    A large danger zone is included when the point is inside it, even if the
    center is farther away than search_radius_km.
    """
    results: list[GeofenceMatch] = []
    for geofence in geofences:
        match = check_geofence(lat, lng, geofence, warning_buffer_km=search_radius_km)
        if match.distance_km <= max(search_radius_km, match.geofence.radius_km):
            results.append(match)
    return [match.as_dict() for match in sorted(results, key=lambda item: item.distance_km)]


def nearest_geofence(
    lat: float,
    lng: float,
    geofences: Iterable[Geofence | Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Return the nearest geofence as a JSON-friendly dictionary."""
    matches = check_geofences(lat, lng, geofences, include_outside=True)
    if not matches:
        return None
    return matches[0].as_dict()


def active_geofence_alerts(
    lat: float,
    lng: float,
    geofences: Iterable[Geofence | Mapping[str, Any]],
    warning_buffer_km: float = 2.0,
    max_total_radius_km: float | None = None,
) -> list[dict[str, Any]]:
    """
    Return warning records for zones the user is inside or approaching.

    The output is designed for API/UI use and includes a clear message.
    """
    alerts = []
    for match in check_geofences(
        lat,
        lng,
        geofences,
        warning_buffer_km=warning_buffer_km,
        max_total_radius_km=max_total_radius_km,
    ):
        zone = match.geofence
        if match.inside:
            message = f"You are inside {zone.name}, a {zone.risk_level} risk zone."
        else:
            message = (
                f"You are {match.margin_km:.1f} km from {zone.name}, "
                f"a {zone.risk_level} risk zone."
            )
        alerts.append(
            {
                "zone_id": zone.id,
                "zone_name": zone.name,
                "status": match.status,
                "risk_level": zone.risk_level,
                "risk_score": zone.risk_score,
                "distance_km": round(match.distance_km, 3),
                "inside_zone": match.inside,
                "message": message,
                "advisory": zone.metadata.get("advisory", ""),
            }
        )
    return alerts


def geofence_transition(
    previous_lat: float,
    previous_lng: float,
    current_lat: float,
    current_lng: float,
    geofence: Geofence | Mapping[str, Any],
) -> dict[str, Any]:
    """Detect whether movement entered, exited, stayed inside, or stayed outside a zone."""
    previous = check_geofence(previous_lat, previous_lng, geofence)
    current = check_geofence(current_lat, current_lng, geofence)

    if not previous.inside and current.inside:
        event = "entered"
    elif previous.inside and not current.inside:
        event = "exited"
    elif current.inside:
        event = "inside"
    else:
        event = "outside"

    return {
        "zone_id": current.geofence.id,
        "zone_name": current.geofence.name,
        "event": event,
        "previous": previous.as_dict(),
        "current": current.as_dict(),
    }


def risk_multiplier_for_match(match: GeofenceMatch) -> float:
    """
    Return a 0-1 proximity multiplier for risk scoring.

    Inside a zone returns 1.0. Outside risk decays over 10 km from the boundary.
    """
    if match.inside:
        return 1.0
    return max(0.0, 1 - (match.margin_km / 10.0))


def normalize_geofence(geofence: Geofence | Mapping[str, Any]) -> Geofence:
    if isinstance(geofence, Geofence):
        return geofence
    return Geofence.from_mapping(geofence)


def load_danger_zones() -> list[dict[str, Any]]:
    """Load RoadSoS danger zones without making callers depend on route helpers."""
    from app.routes._data import load_json

    return load_json("danger_zones.json")
