from typing import Any

from app.services.route_service import get_safest_route


def _has_coordinates(result: dict[str, Any]) -> bool:
    return result.get("lat") is not None and result.get("lng") is not None


def attach_route_waypoints(
    results: list[dict[str, Any]],
    lat: float | None,
    lng: float | None,
) -> list[dict[str, Any]]:
    """
    Add Dijkstra route waypoints from the user location to the nearest place.

    Endpoints keep returning their existing list shape; when user coordinates
    are present, the nearest routable item gets an ordered coordinate list the
    frontend can draw directly.
    """
    if lat is None or lng is None:
        return results

    routed_results = [{**result, "route_waypoints": []} for result in results]
    nearest_index = next(
        (index for index, result in enumerate(routed_results) if _has_coordinates(result)),
        None,
    )
    if nearest_index is None:
        return routed_results

    nearest = routed_results[nearest_index]
    start_id = "user_location"
    destination_id = str(nearest.get("id") or "nearest_destination")
    route = get_safest_route(
        nodes=[
            {
                "id": start_id,
                "name": "User location",
                "lat": lat,
                "lng": lng,
            },
            {
                "id": destination_id,
                "name": nearest.get("name") or "Nearest destination",
                "lat": nearest["lat"],
                "lng": nearest["lng"],
            },
        ],
        start=start_id,
        goal=destination_id,
    )

    nearest["route_waypoints"] = [
        {"lat": point["lat"], "lng": point["lng"]}
        for point in route.get("route_points", [])
    ]
    nearest["route"] = {
        "algorithm": "dijkstra",
        "reachable": route.get("reachable", False),
        "total_distance_km": route.get("total_distance_km"),
        "total_cost": route.get("total_cost"),
        "total_risk_score": route.get("total_risk_score"),
    }

    return routed_results
