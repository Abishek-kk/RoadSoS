import json
import math
import re
import logging
import httpx
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
logger = logging.getLogger("roadsos.data")


def load_json(name: str) -> list[dict[str, Any]]:
    with (DATA_DIR / name).open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("services"), list):
        return data["services"]
    return data


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
    rows: list[dict[str, Any]], lat: float | None, lng: float | None
) -> list[dict[str, Any]]:
    if lat is None or lng is None:
        return [normalize_coordinates(row) for row in rows]

    enriched = []
    for row in rows:
        normalized = normalize_coordinates(row)
        row_lat = normalized.get("lat")
        row_lng = normalized.get("lng")
        if row_lat is None or row_lng is None:
            enriched.append({**normalized, "distance_km": None})
            continue
        enriched.append(
            {
                **normalized,
                "distance_km": distance_km(lat, lng, float(row_lat), float(row_lng)),
            }
        )

    return sorted(
        enriched,
        key=lambda row: row["distance_km"] if row["distance_km"] is not None else float("inf"),
    )


def normalize_coordinates(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("lat") is not None and row.get("lng") is not None:
        return row

    location_link = str(row.get("location_link") or "")
    match = re.search(r"[?&]q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", location_link)
    if not match:
        return row

    return {**row, "lat": float(match.group(1)), "lng": float(match.group(2))}


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


async def fetch_osm_amenities(lat: float, lng: float, amenity: str) -> list[dict[str, Any]]:
    """
    Fetches amenities (hospital or police) near the given lat/lng from OpenStreetMap.
    """
    url = "https://nominatim.openstreetmap.org/search"
    # Bounding box of ~22km around the given coordinate
    viewbox = f"{lng - 0.2},{lat + 0.2},{lng + 0.2},{lat - 0.2}"
    params = {
        "q": amenity,
        "lat": lat,
        "lon": lng,
        "viewbox": viewbox,
        "bounded": 1,
        "format": "json",
        "addressdetails": 1,
        "extratags": 1,
        "limit": 15,
    }
    headers = {
        "User-Agent": "RoadSoSApp/1.0 (contact: team_accelerate@roadsos.app)"
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                elements = response.json()
                results = []
                for item in elements:
                    try:
                        osm_lat = float(item["lat"])
                        osm_lng = float(item["lon"])
                        
                        address_dict = item.get("address", {})
                        name = (
                            address_dict.get(amenity)
                            or address_dict.get("amenity")
                            or address_dict.get("name")
                            or item.get("display_name", "").split(",")[0]
                        )
                        
                        addr_parts = []
                        for key in ["road", "suburb", "city", "county", "state"]:
                            val = address_dict.get(key)
                            if val:
                                addr_parts.append(val)
                        address = ", ".join(addr_parts) if addr_parts else item.get("display_name", "")
                        
                        # Retrieve and clean phone details
                        extratags = item.get("extratags") or {}
                        raw_phone = (
                            extratags.get("phone")
                            or extratags.get("contact:phone")
                            or address_dict.get("phone")
                            or ""
                        )
                        fallback_phone = "108" if amenity == "hospital" else "100"
                        phone = clean_phone_number(raw_phone, fallback_phone)
                        
                        results.append({
                            "id": f"OSM_{item['osm_type']}_{item['osm_id']}",
                            "name": name,
                            "city": address_dict.get("city") or address_dict.get("town") or address_dict.get("village") or "",
                            "state": address_dict.get("state") or "",
                            "address": address,
                            "lat": osm_lat,
                            "lng": osm_lng,
                            "phone": phone,
                            "distance_km": distance_km(lat, lng, osm_lat, osm_lng)
                        })
                    except Exception as parse_err:
                        logger.error(f"Error parsing OSM item: {parse_err}")
                
                results.sort(key=lambda x: x["distance_km"])
                return results
            else:
                logger.error(f"Nominatim returned status code {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Error fetching amenities from OSM: {e}", exc_info=True)
    return []
