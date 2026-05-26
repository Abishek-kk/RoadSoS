# route_service.py — Dijkstra safe route calc
from typing import Any, Iterable, Mapping, List, Optional
from app.algorithms import dijkstra
from app.algorithms.geofencing import load_danger_zones
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
