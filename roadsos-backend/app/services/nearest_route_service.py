from typing import Any

from app.services.route_service import get_safest_route


def attach_route_waypoints(
    results: list[dict[str, Any]],
    lat: float | None,
    lng: float | None,
) -> list[dict[str, Any]]:
    """
    Add Dijkstra route waypoints from the user location to each returned place.

    Endpoints keep returning their existing list shape; when user coordinates
    are present, every routable item gets an ordered coordinate list the
    frontend can draw directly.
    """
    if lat is None or lng is None:
        return results

    routed_results: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        routed = dict(result)
        destination_lat = routed.get("lat")
        destination_lng = routed.get("lng")

        if destination_lat is None or destination_lng is None:
            routed["route_waypoints"] = []
            routed_results.append(routed)
            continue

        start_id = "user_location"
        destination_id = str(routed.get("id") or f"destination_{index}")
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
                    "name": routed.get("name") or "Destination",
                    "lat": destination_lat,
                    "lng": destination_lng,
                },
            ],
            start=start_id,
            goal=destination_id,
        )

        routed["route_waypoints"] = [
            {"lat": point["lat"], "lng": point["lng"]}
            for point in route.get("route_points", [])
        ]
        routed_results.append(routed)

    return routed_results
