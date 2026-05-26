"""
haversine.py - GPS distance and navigation helpers.

RoadSoS uses these pure functions for nearby services, geofencing, and route
scoring. Distances are in kilometers unless a function name says otherwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


EARTH_RADIUS_KM = 6371.0
EARTH_RADIUS_M = EARTH_RADIUS_KM * 1000


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lng: float

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "Coordinate":
        return cls(lat=float(item["lat"]), lng=float(item["lng"]))

    def as_dict(self) -> dict[str, float]:
        return {"lat": self.lat, "lng": self.lng}


def haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance between two coordinates in kilometers."""
    point1 = validate_coordinate(lat1, lng1)
    point2 = validate_coordinate(lat2, lng2)
    d_lat = math.radians(point2.lat - point1.lat)
    d_lng = math.radians(point2.lng - point1.lng)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(point1.lat))
        * math.cos(math.radians(point2.lat))
        * math.sin(d_lng / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance between two coordinates in meters."""
    return haversine_distance_km(lat1, lng1, lat2, lng2) * 1000


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float, precision: int | None = 1) -> float:
    """
    Compatibility wrapper used by the rest of the backend.

    By default this rounds to one decimal place to match app.routes._data.
    Pass precision=None for the raw floating-point distance.
    """
    distance = haversine_distance_km(lat1, lng1, lat2, lng2)
    return distance if precision is None else round(distance, precision)


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float, precision: int | None = 0) -> float:
    distance = haversine_distance_m(lat1, lng1, lat2, lng2)
    return distance if precision is None else round(distance, precision)


def bearing_degrees(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return initial bearing from point 1 to point 2 in degrees from north."""
    point1 = validate_coordinate(lat1, lng1)
    point2 = validate_coordinate(lat2, lng2)
    lat1_rad = math.radians(point1.lat)
    lat2_rad = math.radians(point2.lat)
    d_lng = math.radians(point2.lng - point1.lng)

    y = math.sin(d_lng) * math.cos(lat2_rad)
    x = (
        math.cos(lat1_rad) * math.sin(lat2_rad)
        - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lng)
    )
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_direction(bearing: float) -> str:
    """Convert a bearing in degrees to a 16-point compass direction."""
    directions = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    index = int((float(bearing) + 11.25) // 22.5) % 16
    return directions[index]


def destination_point(lat: float, lng: float, distance_km_value: float, bearing: float) -> Coordinate:
    """Return the coordinate reached by moving distance along an initial bearing."""
    start = validate_coordinate(lat, lng)
    angular_distance = float(distance_km_value) / EARTH_RADIUS_KM
    bearing_rad = math.radians(float(bearing))
    lat1 = math.radians(start.lat)
    lng1 = math.radians(start.lng)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    lng2 = lng1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )

    return Coordinate(
        lat=math.degrees(lat2),
        lng=normalize_longitude(math.degrees(lng2)),
    )


def midpoint(lat1: float, lng1: float, lat2: float, lng2: float) -> Coordinate:
    """Return the geographic midpoint between two coordinates."""
    point1 = validate_coordinate(lat1, lng1)
    point2 = validate_coordinate(lat2, lng2)
    lat1_rad = math.radians(point1.lat)
    lng1_rad = math.radians(point1.lng)
    lat2_rad = math.radians(point2.lat)
    d_lng = math.radians(point2.lng - point1.lng)

    bx = math.cos(lat2_rad) * math.cos(d_lng)
    by = math.cos(lat2_rad) * math.sin(d_lng)
    lat3 = math.atan2(
        math.sin(lat1_rad) + math.sin(lat2_rad),
        math.sqrt((math.cos(lat1_rad) + bx) ** 2 + by**2),
    )
    lng3 = lng1_rad + math.atan2(by, math.cos(lat1_rad) + bx)
    return Coordinate(lat=math.degrees(lat3), lng=normalize_longitude(math.degrees(lng3)))


def bounding_box(lat: float, lng: float, radius_km: float) -> dict[str, float]:
    """Return an approximate lat/lng bounding box around a point."""
    center = validate_coordinate(lat, lng)
    radius = max(float(radius_km), 0.0)
    lat_delta = math.degrees(radius / EARTH_RADIUS_KM)
    lng_delta = math.degrees(radius / (EARTH_RADIUS_KM * math.cos(math.radians(center.lat))))

    return {
        "min_lat": max(-90.0, center.lat - lat_delta),
        "max_lat": min(90.0, center.lat + lat_delta),
        "min_lng": normalize_longitude(center.lng - lng_delta),
        "max_lng": normalize_longitude(center.lng + lng_delta),
    }


def with_distances(
    rows: Iterable[Mapping[str, Any]],
    lat: float,
    lng: float,
    lat_key: str = "lat",
    lng_key: str = "lng",
) -> list[dict[str, Any]]:
    """Return rows enriched with distance_km, sorted nearest first."""
    origin = validate_coordinate(lat, lng)
    enriched: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        if item.get(lat_key) is None or item.get(lng_key) is None:
            item["distance_km"] = None
        else:
            item["distance_km"] = distance_km(
                origin.lat,
                origin.lng,
                float(item[lat_key]),
                float(item[lng_key]),
            )
        enriched.append(item)

    return sorted(
        enriched,
        key=lambda item: item["distance_km"] if item["distance_km"] is not None else math.inf,
    )


def nearest_point(
    lat: float,
    lng: float,
    rows: Iterable[Mapping[str, Any]],
    lat_key: str = "lat",
    lng_key: str = "lng",
) -> dict[str, Any] | None:
    """Return the nearest row with distance_km, or None for an empty iterable."""
    ranked = with_distances(rows, lat, lng, lat_key=lat_key, lng_key=lng_key)
    return ranked[0] if ranked else None


def points_within_radius(
    lat: float,
    lng: float,
    rows: Iterable[Mapping[str, Any]],
    radius_km: float,
    lat_key: str = "lat",
    lng_key: str = "lng",
) -> list[dict[str, Any]]:
    """Return rows within radius_km, sorted nearest first."""
    ranked = with_distances(rows, lat, lng, lat_key=lat_key, lng_key=lng_key)
    return [
        row
        for row in ranked
        if row["distance_km"] is not None and float(row["distance_km"]) <= float(radius_km)
    ]


def validate_coordinate(lat: float, lng: float) -> Coordinate:
    lat = float(lat)
    lng = float(lng)
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}.")
    if not -180 <= lng <= 180:
        raise ValueError(f"Longitude must be between -180 and 180, got {lng}.")
    return Coordinate(lat=lat, lng=lng)


def normalize_longitude(lng: float) -> float:
    """Normalize longitude to the [-180, 180] range."""
    return ((float(lng) + 540) % 360) - 180


# Common aliases used in algorithm examples and older modules.
haversine_km = haversine_distance_km
calculate_distance = distance_km
