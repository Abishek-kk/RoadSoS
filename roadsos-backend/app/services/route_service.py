# route_service.py — Dijkstra safe route calc
import logging
from typing import Any, Iterable, Mapping, List, Optional

import httpx

from app.algorithms.haversine import distance_km as haversine_distance_km
from app.algorithms import dijkstra
from app.algorithms.geofencing import load_danger_zones
from app.config import get_osrm_base_url
from app.routes._data import load_json

# Re-expose classes and core functions
RouteNode = dijkstra.RouteNode
RouteEdge = dijkstra.RouteEdge
RouteResult = dijkstra.RouteResult
shortest_path = dijkstra.shortest_path
safest_path = dijkstra.safest_path
build_graph = dijkstra.build_graph
build_complete_graph = dijkstra.build_complete_graph
severity_points = dijkstra.severity_points
segment_risk = dijkstra.segment_risk
edge_cost = dijkstra.edge_cost

logger = logging.getLogger("roadsos.routes")


def get_safest_route(
    nodes: Iterable[RouteNode | Mapping[str, Any]],
    start: dijkstra.NodeId,
    goal: dijkstra.NodeId,
    edges: Iterable[Mapping[str, Any]] | None = None,
    max_edge_km: float | None = None,
) -> dict[str, Any]:
    """
    Computes the safest and most optimal route between two points on the map,
    penalizing segments based on known danger zones and active road alerts.
    """
    # Load all danger zones
    danger_zones = load_danger_zones()

    # Load active alerts
    alerts_data = load_json("road_alerts.json")
    active_alerts = [
        alert for alert in alerts_data
        if str(alert.get("status", "")).lower() in {"active", "open", "ongoing"}
    ]

    return dijkstra.find_safest_route(
        nodes=nodes,
        start=start,
        goal=goal,
        edges=edges,
        danger_zones=danger_zones,
        alerts=active_alerts,
        max_edge_km=max_edge_km,
    )


def get_route_between_points(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    destination_id: str = "destination",
    destination_name: str = "Destination",
) -> dict[str, Any]:
    """
    Return route geometry, distance, and ETA.

    If OSRM_BASE_URL is configured, OSRM is tried first. Any routing failure
    falls back to the local Dijkstra route so emergency data still reaches the
    client.
    """
    osrm_route = fetch_osrm_route(from_lat, from_lng, to_lat, to_lng)
    if osrm_route:
        return {
            **osrm_route,
            "destination_id": destination_id,
            "destination_name": destination_name,
        }

    start_id = "user_location"
    try:
        route = get_safest_route(
            nodes=[
                {
                    "id": start_id,
                    "name": "User location",
                    "lat": from_lat,
                    "lng": from_lng,
                },
                {
                    "id": destination_id,
                    "name": destination_name,
                    "lat": to_lat,
                    "lng": to_lng,
                },
            ],
            start=start_id,
            goal=destination_id,
        )
        route_points = [
            {"lat": float(point["lat"]), "lng": float(point["lng"])}
            for point in route.get("route_points", [])
            if point.get("lat") is not None and point.get("lng") is not None
        ]
        if route.get("reachable", True) and route_points:
            distance = float(route.get("total_distance_km") or haversine_distance_km(from_lat, from_lng, to_lat, to_lng))
            eta_minutes = estimate_drive_minutes(distance)
            return {
                "provider": "local_dijkstra",
                "reachable": True,
                "polyline": route_points,
                "route_points": route_points,
                "distance_km": round(distance, 2),
                "total_distance_km": round(distance, 2),
                "eta_minutes": eta_minutes,
                "travel_time_minutes": eta_minutes,
                "eta": format_eta(eta_minutes),
                "total_cost": route.get("total_cost"),
                "total_risk_score": route.get("total_risk_score"),
                "destination_id": destination_id,
                "destination_name": destination_name,
            }
    except Exception as exc:
        logger.warning("Local Dijkstra route failed; using straight-line fallback. Error: %s", exc)

    return straight_line_route(
        from_lat,
        from_lng,
        to_lat,
        to_lng,
        destination_id=destination_id,
        destination_name=destination_name,
    )


def fetch_osrm_route(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
) -> dict[str, Any] | None:
    base_url = get_osrm_base_url()
    if not base_url:
        return None

    url = (
        f"{base_url}/route/v1/driving/"
        f"{from_lng},{from_lat};{to_lng},{to_lat}"
    )
    params = {"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"}
    try:
        response = httpx.get(url, params=params, timeout=4.0)
        response.raise_for_status()
        payload = response.json()
        route = (payload.get("routes") or [None])[0]
        if not route:
            return None
        coordinates = ((route.get("geometry") or {}).get("coordinates") or [])
        polyline = [
            {"lat": float(lat), "lng": float(lng)}
            for lng, lat in coordinates
            if lat is not None and lng is not None
        ]
        if not polyline:
            return None
        distance = round(float(route.get("distance") or 0) / 1000.0, 2)
        duration_seconds = float(route.get("duration") or 0)
        eta_minutes = max(1, int(round(duration_seconds / 60.0))) if duration_seconds else estimate_drive_minutes(distance)
        return {
            "provider": "osrm",
            "reachable": True,
            "polyline": polyline,
            "route_points": polyline,
            "distance_km": distance,
            "total_distance_km": distance,
            "eta_minutes": eta_minutes,
            "travel_time_minutes": eta_minutes,
            "duration_seconds": round(duration_seconds, 1),
            "eta": format_eta(eta_minutes),
        }
    except Exception as exc:
        logger.warning("OSRM route failed; falling back to local route. Error: %s", exc)
        return None


def straight_line_route(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    destination_id: str = "destination",
    destination_name: str = "Destination",
) -> dict[str, Any]:
    distance = haversine_distance_km(from_lat, from_lng, to_lat, to_lng)
    eta_minutes = estimate_drive_minutes(distance)
    points = [
        {"lat": from_lat, "lng": from_lng},
        {"lat": to_lat, "lng": to_lng},
    ]
    return {
        "provider": "straight_line_fallback",
        "reachable": True,
        "polyline": points,
        "route_points": points,
        "distance_km": round(distance, 2),
        "total_distance_km": round(distance, 2),
        "eta_minutes": eta_minutes,
        "travel_time_minutes": eta_minutes,
        "eta": format_eta(eta_minutes),
        "destination_id": destination_id,
        "destination_name": destination_name,
    }


def estimate_drive_minutes(distance: float, average_speed_kmph: float = 35.0) -> int:
    speed = max(float(average_speed_kmph), 1.0)
    return max(1, int(round((float(distance) / speed) * 60)))


def format_eta(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    remainder = minutes % 60
    if remainder == 0:
        return f"{hours} hr"
    return f"{hours} hr {remainder} min"
