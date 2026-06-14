"""
route.py — Safest-route planning endpoint.

Combines the bundled danger-zone and road-alert data with nearby hospitals
and police stations to compute a risk-weighted path using Dijkstra's algorithm.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Any

from app.routes._data import load_json, with_distance
from app.algorithms.dijkstra import find_safest_route


router = APIRouter(prefix="/route", tags=["Route Planning"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk_level(total_risk: float) -> str:
    """Derive a human-readable risk level from the cumulative risk score."""
    if total_risk < 2:
        return "low"
    if total_risk < 5:
        return "medium"
    if total_risk < 8:
        return "high"
    return "critical"


def _build_waypoints(
    lat: float,
    lng: float,
    hospitals: list[dict[str, Any]],
    police_stations: list[dict[str, Any]],
    max_waypoint_km: float = 30.0,
    limit_per_type: int = 5,
) -> list[dict[str, Any]]:
    """
    Select nearby hospitals and police stations to serve as route waypoints.

    Returns a list of dicts compatible with ``find_safest_route`` nodes:
    ``{id, lat, lng, name}``.
    """
    waypoints: list[dict[str, Any]] = []

    nearby_hospitals = with_distance(
        hospitals, lat, lng, max_km=max_waypoint_km, limit=limit_per_type
    )
    for h in nearby_hospitals:
        if h.get("lat") is None or h.get("lng") is None:
            continue
        waypoints.append({
            "id": f"hospital_{h.get('id', '')}",
            "lat": h["lat"],
            "lng": h["lng"],
            "name": h.get("name", "Hospital"),
        })

    nearby_police = with_distance(
        police_stations, lat, lng, max_km=max_waypoint_km, limit=limit_per_type
    )
    for p in nearby_police:
        if p.get("lat") is None or p.get("lng") is None:
            continue
        waypoints.append({
            "id": f"police_{p.get('id', '')}",
            "lat": p["lat"],
            "lng": p["lng"],
            "name": p.get("name", "Police Station"),
        })

    return waypoints


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("")
async def get_safest_route(
    from_lat: float = Query(..., description="Origin latitude"),
    from_lng: float = Query(..., description="Origin longitude"),
    to_lat: float = Query(..., description="Destination latitude"),
    to_lng: float = Query(..., description="Destination longitude"),
    max_waypoint_km: float = Query(
        30.0, description="Max radius (km) to pull hospital/police waypoints"
    ),
    limit_per_type: int = Query(
        5, description="Max hospitals and police stations to include as waypoints"
    ),
    max_edge_km: float | None = Query(
        None, description="Max straight-line km between connected nodes"
    ),
) -> dict[str, Any]:
    """
    Compute the safest route between two GPS coordinates.

    The algorithm builds a complete graph of the origin, destination, and
    nearby hospitals / police-stations, weighs each edge with distance and
    danger-zone / road-alert risk, then runs Dijkstra to find the
    lowest-cost path.
    """
    # ---- Load bundled data ------------------------------------------------
    try:
        danger_zones = load_json("danger_zones.json")
    except FileNotFoundError:
        danger_zones = []

    try:
        road_alerts = load_json("road_alerts.json")
    except FileNotFoundError:
        road_alerts = []

    try:
        hospitals = load_json("hospitals.json")
    except FileNotFoundError:
        hospitals = []

    try:
        police_stations = load_json("police_stations.json")
    except FileNotFoundError:
        police_stations = []

    # ---- Build node list --------------------------------------------------
    origin_node = {
        "id": "origin",
        "lat": from_lat,
        "lng": from_lng,
        "name": "Origin",
    }
    destination_node = {
        "id": "destination",
        "lat": to_lat,
        "lng": to_lng,
        "name": "Destination",
    }

    waypoints = _build_waypoints(
        from_lat,
        from_lng,
        hospitals,
        police_stations,
        max_waypoint_km=max_waypoint_km,
        limit_per_type=limit_per_type,
    )

    # Include destination waypoints that are near the end of the route too
    dest_waypoints = _build_waypoints(
        to_lat,
        to_lng,
        hospitals,
        police_stations,
        max_waypoint_km=max_waypoint_km,
        limit_per_type=limit_per_type,
    )

    # Deduplicate by id
    seen_ids: set[str] = set()
    all_waypoints: list[dict[str, Any]] = []
    for wp in waypoints + dest_waypoints:
        if wp["id"] not in seen_ids:
            seen_ids.add(wp["id"])
            all_waypoints.append(wp)

    nodes: list[dict[str, Any]] = [origin_node, destination_node] + all_waypoints

    # ---- Run Dijkstra -----------------------------------------------------
    result = find_safest_route(
        nodes=nodes,
        start="origin",
        goal="destination",
        danger_zones=danger_zones,
        alerts=road_alerts,
        max_edge_km=max_edge_km,
    )

    if not result.get("reachable", True):
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": "No route found between the given coordinates.",
            },
        )

    return {
        "success": True,
        "path": result["path"],
        "total_distance_km": result["total_distance_km"],
        "total_risk_score": result["total_risk_score"],
        "risk_level": _risk_level(result["total_risk_score"]),
        "route_points": result["route_points"],
        "edges": result.get("edges", []),
    }