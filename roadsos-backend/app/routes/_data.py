import json
import math
import re
import logging
import httpx
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
logger = logging.getLogger("roadsos.data")
_JSON_CACHE: dict[str, list[dict[str, Any]]] = {}
FOLDER_DATASETS = {
    "hospitals.json": "hospitals",
    "police_stations.json": "police_stations",
    "towing.json": "towing_services",
}


def cache_clear() -> None:
    """Clear cached JSON data for tests or development reload scenarios."""
    _JSON_CACHE.clear()


def load_json(name: str) -> list[dict[str, Any]]:
    if name in _JSON_CACHE:
        return _JSON_CACHE[name]

    dataset_dir = FOLDER_DATASETS.get(name)
    if dataset_dir and (DATA_DIR / dataset_dir).is_dir():
        data: list[dict[str, Any]] = []
        for path in sorted((DATA_DIR / dataset_dir).glob("*.json")):
            with path.open("r", encoding="utf-8") as f:
                district_data = json.load(f)
            if isinstance(district_data, list):
                data.extend(
                    normalize_dataset_row(row, dataset_dir, path.stem)
                    for row in district_data
                    if isinstance(row, dict)
                )
            elif isinstance(district_data, dict) and isinstance(district_data.get("services"), list):
                data.extend(
                    normalize_dataset_row(row, dataset_dir, path.stem)
                    for row in district_data["services"]
                    if isinstance(row, dict)
                )
        _JSON_CACHE[name] = data
        return _JSON_CACHE[name]

    with (DATA_DIR / name).open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        _JSON_CACHE[name] = [
            normalize_dataset_row(row, None, None)
            for row in data
            if isinstance(row, dict)
        ]
        return _JSON_CACHE[name]
    if isinstance(data, dict) and isinstance(data.get("services"), list):
        _JSON_CACHE[name] = [
            normalize_dataset_row(row, None, None)
            for row in data["services"]
            if isinstance(row, dict)
        ]
        return _JSON_CACHE[name]

    _JSON_CACHE[name] = data
    return _JSON_CACHE[name]


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return round(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)


def with_distance(
    rows: list[dict[str, Any]],
    lat: float | None,
    lng: float | None,
    max_km: float | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Enrich rows with `distance_km` from (lat,lng), sort by distance and
    optionally filter to a `max_km` radius and/or return only `limit` items.

    - When `lat` or `lng` is None the original rows are returned with
      normalized coordinates but without distances.
    - `max_km` when provided will exclude rows with distance > max_km.
    - `limit` when provided returns at most that many closest results.
    """
    if lat is None or lng is None:
        return [normalize_coordinates(row) for row in rows]

    enriched: list[dict[str, Any]] = []
    for row in rows:
        normalized = normalize_coordinates(row)
        row_lat = normalized.get("lat")
        row_lng = normalized.get("lng")
        if row_lat is None or row_lng is None:
            enriched.append({**normalized, "distance_km": None})
            continue
        dist = distance_km(lat, lng, float(row_lat), float(row_lng))
        enriched.append({**normalized, "distance_km": dist})

    enriched_sorted = sorted(
        enriched,
        key=lambda row: row["distance_km"] if row["distance_km"] is not None else float("inf"),
    )

    if max_km is not None:
        enriched_sorted = [
            r
            for r in enriched_sorted
            if r.get("distance_km") is not None and r["distance_km"] <= float(max_km)
        ]

    if limit is not None and isinstance(limit, int) and limit > 0:
        enriched_sorted = enriched_sorted[:limit]

    return enriched_sorted


def nearest_with_fallback(
    rows: list[dict[str, Any]],
    lat: float | None,
    lng: float | None,
    max_km: float,
    limit: int = 20,
    fallback_limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return rows inside `max_km`; when none are available, return the nearest
    known rows instead of an empty list.
    """
    nearby = with_distance(rows, lat, lng, max_km=max_km, limit=limit)
    if nearby or lat is None or lng is None:
        return nearby

    return with_distance(rows, lat, lng, limit=fallback_limit)


def normalize_coordinates(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("lat") is not None and row.get("lng") is not None:
        return row

    if row.get("latitude") is not None and row.get("longitude") is not None:
        return {
            **row,
            "lat": float(row["latitude"]),
            "lng": float(row["longitude"]),
        }

    location_link = str(row.get("location_link") or "")
    match = re.search(
        r"[?&]q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", location_link
    )
    if not match:
        return row

    return {**row, "lat": float(match.group(1)), "lng": float(match.group(2))}


def normalize_dataset_row(
    row: dict[str, Any],
    dataset_dir: str | None,
    district_hint: str | None,
) -> dict[str, Any]:
    normalized = normalize_coordinates(row)

    if not normalized.get("name") and normalized.get("station_name"):
        normalized = {**normalized, "name": normalized["station_name"]}

    if dataset_dir == "police_stations":
        normalized = {
            **normalized,
            "district": normalized.get("district") or district_hint,
            "city": normalized.get("city") or normalized.get("district") or district_hint,
            "state": normalized.get("state") or "Tamil Nadu",
            "type": normalized.get("type") or "Police Station",
        }
    elif dataset_dir == "hospitals":
        normalized = {
            **normalized,
            "district": normalized.get("district") or normalized.get("city") or district_hint,
            "state": normalized.get("state") or "Tamil Nadu",
            "type": normalized.get("type") or "Hospital",
        }
    elif dataset_dir == "towing_services":
        normalized = {
            **normalized,
            "district": normalized.get("district") or district_hint,
            "state": normalized.get("state") or "Tamil Nadu",
            "type": normalized.get("type") or "Towing Service",
        }

    return normalized


def clean_phone_number(phone_str: Any, default_fallback: str) -> str:
    if not phone_str:
        return default_fallback
    phone_str = str(phone_str).strip()
    if not phone_str:
        return default_fallback

    # Split by common delimiters
    parts = re.split(r"[/,;]|\band\b", phone_str)
    first_part = parts[0].strip()

    # If the first part has no digits, return fallback
    if not any(char.isdigit() for char in first_part):
        return default_fallback

    return first_part


async def fetch_osm_amenities(
    lat: float, lng: float, amenity: str
) -> list[dict[str, Any]]:
    """
    Fetches amenities (hospital or police) near the given lat/lng using the
    Overpass API.

    Notes:
    - We must fail fast if Overpass is unreachable/slow, because the frontend
      relies on this route and we already have a bundled JSON fallback.
    """
    radius_m = 25000  # 25 km search radius
    overpass_url = "https://overpass-api.de/api/interpreter"

    # Keep the server-side Overpass computation timeout short.
    overpass_query_timeout_s = 4
    query = f"""
    [out:json][timeout:{overpass_query_timeout_s}];
    (
      node["amenity"="{amenity}"](around:{radius_m},{lat},{lng});
      way["amenity"="{amenity}"](around:{radius_m},{lat},{lng});
    );
    out center body qt 20;
    """

    headers = {
        "User-Agent": "RoadSoSApp/1.0 (contact: team_accelerate@roadsos.app)"
    }

    # Fail fast if Overpass is unreachable (connect/read).
    # This endpoint has a fallback; don't block the frontend.
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.post(
                overpass_url,
                data={"data": query},
                headers=headers,
            )
            if response.status_code != 200:
                logger.error(
                    f"Overpass returned status {response.status_code}: {response.text[:300]}"
                )
                return []

            data = response.json()
            elements = data.get("elements", [])
            results: list[dict[str, Any]] = []

            for el in elements:
                try:
                    # For ways, Overpass returns the centroid in "center"
                    if el["type"] == "way":
                        center = el.get("center", {})
                        osm_lat = float(center.get("lat", 0))
                        osm_lng = float(center.get("lon", 0))
                    else:
                        osm_lat = float(el.get("lat", 0))
                        osm_lng = float(el.get("lon", 0))

                    if osm_lat == 0 and osm_lng == 0:
                        continue

                    tags = el.get("tags", {})
                    name = tags.get("name", tags.get("name:en", "Unnamed"))

                    # Build address from available tags
                    addr_parts = []
                    for key in [
                        "addr:street",
                        "addr:suburb",
                        "addr:city",
                        "addr:district",
                        "addr:state",
                    ]:
                        val = tags.get(key)
                        if val:
                            addr_parts.append(val)
                    address = ", ".join(addr_parts) if addr_parts else ""

                    city = (
                        tags.get("addr:city")
                        or tags.get("addr:town")
                        or tags.get("addr:village")
                        or ""
                    )
                    state = tags.get("addr:state", "")

                    # Phone number
                    raw_phone = tags.get("phone") or tags.get(
                        "contact:phone"
                    ) or ""
                    fallback_phone = "108" if amenity == "hospital" else "100"
                    phone = clean_phone_number(raw_phone, fallback_phone)

                    results.append(
                        {
                            "id": f"OSM_{el['type']}_{el['id']}",
                            "name": name,
                            "city": city,
                            "state": state,
                            "address": address,
                            "lat": osm_lat,
                            "lng": osm_lng,
                            "phone": phone,
                            "distance_km": distance_km(lat, lng, osm_lat, osm_lng),
                        }
                    )
                except Exception as parse_err:
                    logger.error(f"Error parsing Overpass element: {parse_err}")

            results.sort(key=lambda x: x["distance_km"])
            return results

    except Exception as e:
        logger.error(
            f"Error fetching amenities from Overpass: {e}", exc_info=True
        )
    return []


async def fetch_overpass_towing(lat: float, lng: float) -> list[dict[str, Any]]:
    """Fetch towing / car-repair services near the given lat/lng using Overpass."""
    radius_m = 25000
    overpass_url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json][timeout:15];
    (
      node["shop"="car_repair"](around:{radius_m},{lat},{lng});
      way["shop"="car_repair"](around:{radius_m},{lat},{lng});
      node["craft"="car_repair"](around:{radius_m},{lat},{lng});
      way["craft"="car_repair"](around:{radius_m},{lat},{lng});
      node["shop"="car"](around:{radius_m},{lat},{lng});
      way["shop"="car"](around:{radius_m},{lat},{lng});
    );
    out center body qt 20;
    """

    headers = {
        "User-Agent": "RoadSoSApp/1.0 (contact: team_accelerate@roadsos.app)"
    }

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.post(
                overpass_url,
                data={"data": query},
                headers=headers,
            )
            if response.status_code != 200:
                logger.error(
                    f"Overpass (towing) returned status {response.status_code}: {response.text[:300]}"
                )
                return []

            data = response.json()
            elements = data.get("elements", [])
            results: list[dict[str, Any]] = []

            for el in elements:
                try:
                    if el["type"] == "way":
                        center = el.get("center", {})
                        osm_lat = float(center.get("lat", 0))
                        osm_lng = float(center.get("lon", 0))
                    else:
                        osm_lat = float(el.get("lat", 0))
                        osm_lng = float(el.get("lon", 0))

                    if osm_lat == 0 and osm_lng == 0:
                        continue

                    tags = el.get("tags", {})
                    name = tags.get(
                        "name", tags.get("name:en", "Car Repair / Towing")
                    )

                    addr_parts = []
                    for key in [
                        "addr:street",
                        "addr:suburb",
                        "addr:city",
                        "addr:district",
                        "addr:state",
                    ]:
                        val = tags.get(key)
                        if val:
                            addr_parts.append(val)
                    address = ", ".join(addr_parts) if addr_parts else ""

                    raw_phone = tags.get("phone") or tags.get(
                        "contact:phone"
                    ) or ""
                    phone = clean_phone_number(raw_phone, "112")

                    # Determine service type from tags
                    svc_type = "Car Repair / Towing"
                    if tags.get("shop") == "car_repair" or tags.get(
                        "craft"
                    ) == "car_repair":
                        svc_type = "Car Repair"
                    elif tags.get("shop") == "car":
                        svc_type = "Car Service"

                    results.append(
                        {
                            "id": f"OSM_{el['type']}_{el['id']}",
                            "name": name,
                            "district": (
                                tags.get("addr:city")
                                or tags.get("addr:district")
                                or ""
                            ),
                            "state": tags.get("addr:state", ""),
                            "address": address,
                            "phone": phone,
                            "type": svc_type,
                            "open_24x7": tags.get(
                                "opening_hours", ""
                            ).lower().startswith("24"),
                            "lat": osm_lat,
                            "lng": osm_lng,
                            "rating": None,
                            "distance_km": distance_km(
                                lat, lng, osm_lat, osm_lng
                            ),
                        }
                    )
                except Exception as parse_err:
                    logger.error(
                        f"Error parsing Overpass towing element: {parse_err}"
                    )

            results.sort(key=lambda x: x["distance_km"])
            return results

    except Exception as e:
        logger.error(
            f"Error fetching towing from Overpass: {e}", exc_info=True
        )
    return []
