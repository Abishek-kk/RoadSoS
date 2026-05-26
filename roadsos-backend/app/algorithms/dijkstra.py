"""
dijkstra.py - shortest and safest route helpers.

The core algorithm is generic: pass an adjacency graph and it returns the
lowest-cost path. RoadSoS-specific helpers add GPS distance and safety penalties
from danger zones or active road alerts.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


NodeId = str


@dataclass(frozen=True)
class RouteNode:
    id: NodeId
    lat: float
    lng: float
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteEdge:
    to: NodeId
    distance_km: float
    risk_score: float = 0.0
    duration_min: float | None = None
    road_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def cost(self) -> float:
        return edge_cost(self.distance_km, self.risk_score)


@dataclass
class RouteResult:
    path: list[NodeId]
    total_cost: float
    total_distance_km: float
    total_risk_score: float
    reachable: bool = True
    edges: list[RouteEdge] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "total_cost": round(self.total_cost, 3),
            "total_distance_km": round(self.total_distance_km, 3),
            "total_risk_score": round(self.total_risk_score, 3),
            "reachable": self.reachable,
            "edges": [
                {
                    "to": edge.to,
                    "distance_km": round(edge.distance_km, 3),
                    "risk_score": round(edge.risk_score, 3),
                    "duration_min": edge.duration_min,
                    "road_name": edge.road_name,
                    "metadata": edge.metadata,
                }
                for edge in self.edges
            ],
        }


Graph = dict[NodeId, list[RouteEdge]]


def dijkstra(graph: Graph, start: NodeId, goal: NodeId) -> RouteResult:
    """
    Return the lowest-cost path from start to goal.

    Edge cost combines distance and risk. If the goal cannot be reached, the
    result has reachable=False and an empty path.
    """
    if start not in graph:
        return unreachable_result()
    if start == goal:
        return RouteResult(
            path=[start],
            total_cost=0.0,
            total_distance_km=0.0,
            total_risk_score=0.0,
        )

    distances: dict[NodeId, float] = {start: 0.0}
    previous: dict[NodeId, tuple[NodeId, RouteEdge]] = {}
    visited: set[NodeId] = set()
    queue: list[tuple[float, NodeId]] = [(0.0, start)]

    while queue:
        current_cost, current = heapq.heappop(queue)
        if current in visited:
            continue
        visited.add(current)

        if current == goal:
            break

        for edge in graph.get(current, []):
            if edge.to in visited:
                continue
            candidate_cost = current_cost + edge.cost
            if candidate_cost < distances.get(edge.to, math.inf):
                distances[edge.to] = candidate_cost
                previous[edge.to] = (current, edge)
                heapq.heappush(queue, (candidate_cost, edge.to))

    if goal not in distances:
        return unreachable_result()

    return build_result(start, goal, distances[goal], previous)


def shortest_path(graph: Graph, start: NodeId, goal: NodeId) -> list[NodeId]:
    """Compatibility helper returning only the node path."""
    return dijkstra(graph, start, goal).path


def safest_path(graph: Graph, start: NodeId, goal: NodeId) -> RouteResult:
    """Alias for dijkstra, named for RoadSoS callers."""
    return dijkstra(graph, start, goal)


def build_result(
    start: NodeId,
    goal: NodeId,
    total_cost: float,
    previous: Mapping[NodeId, tuple[NodeId, RouteEdge]],
) -> RouteResult:
    path = [goal]
    edges_reversed: list[RouteEdge] = []
    current = goal

    while current != start:
        parent, edge = previous[current]
        path.append(parent)
        edges_reversed.append(edge)
        current = parent

    path.reverse()
    edges = list(reversed(edges_reversed))
    return RouteResult(
        path=path,
        total_cost=total_cost,
        total_distance_km=sum(edge.distance_km for edge in edges),
        total_risk_score=sum(edge.risk_score for edge in edges),
        edges=edges,
    )


def unreachable_result() -> RouteResult:
    return RouteResult(
        path=[],
        total_cost=math.inf,
        total_distance_km=math.inf,
        total_risk_score=math.inf,
        reachable=False,
    )


def edge_cost(
    distance_km: float,
    risk_score: float = 0.0,
    risk_weight: float = 0.35,
) -> float:
    """
    Convert distance and risk into a single route cost.

    A risk score of 10 adds about 3.5 km of equivalent cost by default. This
    keeps short detours reasonable while avoiding very dangerous segments.
    """
    distance = max(float(distance_km), 0.0)
    risk = max(float(risk_score), 0.0)
    return distance + (risk * risk_weight)


def add_edge(
    graph: Graph,
    from_node: NodeId,
    to_node: NodeId,
    distance_km: float,
    risk_score: float = 0.0,
    bidirectional: bool = True,
    duration_min: float | None = None,
    road_name: str = "",
    metadata: dict[str, Any] | None = None,
) -> Graph:
    """Add one edge to a graph and optionally add the reverse edge."""
    edge = RouteEdge(
        to=to_node,
        distance_km=float(distance_km),
        risk_score=float(risk_score),
        duration_min=duration_min,
        road_name=road_name,
        metadata=metadata or {},
    )
    graph.setdefault(from_node, []).append(edge)
    graph.setdefault(to_node, [])

    if bidirectional:
        reverse_edge = RouteEdge(
            to=from_node,
            distance_km=float(distance_km),
            risk_score=float(risk_score),
            duration_min=duration_min,
            road_name=road_name,
            metadata=metadata or {},
        )
        graph[to_node].append(reverse_edge)

    return graph


def build_graph(edges: Iterable[Mapping[str, Any]]) -> Graph:
    """
    Build a graph from edge dictionaries.

    Expected keys: from, to, distance_km. Optional keys: risk_score,
    bidirectional, duration_min, road_name, metadata.
    """
    graph: Graph = {}
    for item in edges:
        add_edge(
            graph,
            str(item["from"]),
            str(item["to"]),
            float(item["distance_km"]),
            risk_score=float(item.get("risk_score") or 0),
            bidirectional=bool(item.get("bidirectional", True)),
            duration_min=item.get("duration_min"),
            road_name=str(item.get("road_name") or ""),
            metadata=dict(item.get("metadata") or {}),
        )
    return graph


def build_complete_graph(
    nodes: Iterable[RouteNode | Mapping[str, Any]],
    danger_zones: Iterable[Mapping[str, Any]] | None = None,
    alerts: Iterable[Mapping[str, Any]] | None = None,
    max_edge_km: float | None = None,
) -> tuple[Graph, dict[NodeId, RouteNode]]:
    """
    Build a coordinate graph by connecting nearby nodes.

    This is useful for small in-memory route demos or fallback routing. Real map
    data can pass explicit edges to build_graph instead.
    """
    normalized_nodes = {node.id: node for node in normalize_nodes(nodes)}
    graph: Graph = {node_id: [] for node_id in normalized_nodes}
    node_list = list(normalized_nodes.values())

    for index, source in enumerate(node_list):
        for target in node_list[index + 1 :]:
            distance = haversine_km(source.lat, source.lng, target.lat, target.lng)
            if max_edge_km is not None and distance > max_edge_km:
                continue
            risk = segment_risk(source, target, danger_zones or [], alerts or [])
            add_edge(graph, source.id, target.id, distance, risk_score=risk)

    return graph, normalized_nodes


def find_safest_route(
    nodes: Iterable[RouteNode | Mapping[str, Any]],
    start: NodeId,
    goal: NodeId,
    edges: Iterable[Mapping[str, Any]] | None = None,
    danger_zones: Iterable[Mapping[str, Any]] | None = None,
    alerts: Iterable[Mapping[str, Any]] | None = None,
    max_edge_km: float | None = None,
) -> dict[str, Any]:
    """
    High-level RoadSoS route helper returning a JSON-friendly result.

    Pass explicit edges for real road-network routing. Without edges, the helper
    connects coordinate nodes directly, optionally limited by max_edge_km.
    """
    normalized_nodes = {node.id: node for node in normalize_nodes(nodes)}
    if edges is None:
        graph, normalized_nodes = build_complete_graph(
            normalized_nodes.values(),
            danger_zones=danger_zones,
            alerts=alerts,
            max_edge_km=max_edge_km,
        )
    else:
        graph = build_graph(edges)

    result = safest_path(graph, start, goal)
    route_points = [
        {
            "id": node_id,
            "name": normalized_nodes[node_id].name,
            "lat": normalized_nodes[node_id].lat,
            "lng": normalized_nodes[node_id].lng,
        }
        for node_id in result.path
        if node_id in normalized_nodes
    ]

    payload = result.as_dict()
    payload["route_points"] = route_points
    return payload


def normalize_nodes(nodes: Iterable[RouteNode | Mapping[str, Any]]) -> list[RouteNode]:
    normalized = []
    for index, item in enumerate(nodes):
        if isinstance(item, RouteNode):
            normalized.append(item)
            continue

        node_id = item.get("id") or item.get("node_id") or f"node_{index}"
        normalized.append(
            RouteNode(
                id=str(node_id),
                lat=float(item["lat"]),
                lng=float(item["lng"]),
                name=str(item.get("name") or node_id),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return normalized


def segment_risk(
    source: RouteNode,
    target: RouteNode,
    danger_zones: Iterable[Mapping[str, Any]],
    alerts: Iterable[Mapping[str, Any]],
) -> float:
    """Estimate safety risk for a segment using midpoint proximity."""
    midpoint_lat = (source.lat + target.lat) / 2
    midpoint_lng = (source.lng + target.lng) / 2
    risk = 0.0

    for zone in danger_zones:
        if zone.get("lat") is None or zone.get("lng") is None:
            continue
        distance = haversine_km(midpoint_lat, midpoint_lng, float(zone["lat"]), float(zone["lng"]))
        radius = float(zone.get("radius_km") or 1.0)
        if distance <= radius:
            risk += float(zone.get("risk_score") or 5.0)
        elif distance <= radius + 3.0:
            risk += max(float(zone.get("risk_score") or 5.0) * (1 - ((distance - radius) / 3.0)), 0)

    for alert in alerts:
        if str(alert.get("status", "")).lower() not in {"active", "open", "ongoing"}:
            continue
        location = alert.get("location") or alert
        if location.get("lat") is None or location.get("lng") is None:
            continue
        distance = haversine_km(midpoint_lat, midpoint_lng, float(location["lat"]), float(location["lng"]))
        if distance <= 2.0:
            risk += severity_points(str(alert.get("severity") or "medium"))

    return risk


def severity_points(severity: str) -> float:
    return {
        "low": 2.0,
        "medium": 5.0,
        "moderate": 5.0,
        "high": 8.0,
        "critical": 12.0,
    }.get(severity.strip().lower(), 5.0)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in kilometers."""
    radius = 6371.0
    d_lat = math.radians(float(lat2) - float(lat1))
    d_lng = math.radians(float(lng2) - float(lng1))
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(float(lat1)))
        * math.cos(math.radians(float(lat2)))
        * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
