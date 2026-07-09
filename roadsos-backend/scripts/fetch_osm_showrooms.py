import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SHOWROOM_DIR = Path(__file__).resolve().parents[1] / "data" / "Showrooms"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "RoadSoSApp/1.0 (showroom-data-cleanup)"}

DISTRICT_ALIASES = {
    "Kanniyakumari": ["Kanniyakumari", "Kanyakumari"],
    "Nilgiris": ["The Nilgiris", "Nilgiris"],
    "Tiruchirappalli": ["Tiruchirappalli", "Trichy"],
    "Tirupathur": ["Tirupattur", "Tirupathur"],
}


def overpass_area_query(district_name):
    return f"""
    [out:json][timeout:30];
    area["name"="{district_name}"]["boundary"="administrative"]->.searchArea;
    (
      node["shop"="car"](area.searchArea);
      way["shop"="car"](area.searchArea);
      relation["shop"="car"](area.searchArea);
      node["shop"="motorcycle"](area.searchArea);
      way["shop"="motorcycle"](area.searchArea);
      relation["shop"="motorcycle"](area.searchArea);
    );
    out center tags;
    """


def overpass_radius_query(lat, lng, radius_m):
    return f"""
    [out:json][timeout:25];
    (
      node["shop"="car"](around:{radius_m},{lat},{lng});
      way["shop"="car"](around:{radius_m},{lat},{lng});
      relation["shop"="car"](around:{radius_m},{lat},{lng});
      node["shop"="motorcycle"](around:{radius_m},{lat},{lng});
      way["shop"="motorcycle"](around:{radius_m},{lat},{lng});
      relation["shop"="motorcycle"](around:{radius_m},{lat},{lng});
    );
    out center tags;
    """


def overpass_bbox_query(south, west, north, east):
    return f"""
    [out:json][timeout:30];
    (
      node["shop"="car"]({south},{west},{north},{east});
      way["shop"="car"]({south},{west},{north},{east});
      relation["shop"="car"]({south},{west},{north},{east});
      node["shop"="motorcycle"]({south},{west},{north},{east});
      way["shop"="motorcycle"]({south},{west},{north},{east});
      relation["shop"="motorcycle"]({south},{west},{north},{east});
    );
    out center tags;
    """


def fetch_overpass(query, attempts=3):
    payload = urlencode({"data": query}).encode("utf-8")
    request = Request(OVERPASS_URL, data=payload, headers=HEADERS)
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in {429, 504} or attempt == attempts:
                raise
            time.sleep(10 * attempt)
    return {"elements": []}


def first_tag(tags, *keys):
    for key in keys:
        value = tags.get(key)
        if value:
            return str(value).strip()
    return ""


def build_address(tags):
    parts = [
        first_tag(tags, "addr:housenumber"),
        first_tag(tags, "addr:street"),
        first_tag(tags, "addr:suburb", "addr:neighbourhood"),
        first_tag(tags, "addr:city", "addr:town", "addr:village"),
        first_tag(tags, "addr:district"),
        first_tag(tags, "addr:state"),
        first_tag(tags, "addr:postcode"),
    ]
    return ", ".join(part for part in parts if part)


def normalize_element(element, district, index):
    tags = element.get("tags", {})
    center = element.get("center", {})
    lat = element.get("lat", center.get("lat"))
    lng = element.get("lon", center.get("lon"))
    shop = tags.get("shop", "")
    showroom_type = "Bike Showroom" if shop == "motorcycle" else "Car Showroom"

    return {
        "id": f"OSM_{district.upper().replace(' ', '_')}_{index:04d}",
        "name": first_tag(tags, "name", "brand", "operator") or "Unnamed Showroom",
        "district": district,
        "city": first_tag(tags, "addr:city", "addr:town", "addr:village"),
        "state": first_tag(tags, "addr:state") or "Tamil Nadu",
        "address": build_address(tags),
        "phone": first_tag(tags, "phone", "contact:phone"),
        "type": showroom_type,
        "open_24x7": False,
        "lat": float(lat),
        "lng": float(lng),
        "pincode": first_tag(tags, "addr:postcode"),
        "zone": "OSM",
        "source": "openstreetmap",
        "source_id": f"{element.get('type')}/{element.get('id')}",
        "verification_status": "osm_verified",
    }


def district_center(path):
    records = json.loads(path.read_text(encoding="utf-8-sig"))
    coords = [
        (float(record["lat"]), float(record["lng"]))
        for record in records
        if record.get("lat") is not None and record.get("lng") is not None
    ]
    if not coords:
        return None
    lat = sum(coord[0] for coord in coords) / len(coords)
    lng = sum(coord[1] for coord in coords) / len(coords)
    return lat, lng


def district_bounds(path, margin=0.08):
    records = json.loads(path.read_text(encoding="utf-8-sig"))
    coords = [
        (float(record["lat"]), float(record["lng"]))
        for record in records
        if record.get("lat") is not None and record.get("lng") is not None
    ]
    if not coords:
        return None
    lats = [coord[0] for coord in coords]
    lngs = [coord[1] for coord in coords]
    return (
        min(lats) - margin,
        max(lats) + margin,
        min(lngs) - margin,
        max(lngs) + margin,
    )


def element_coordinates(element):
    center = element.get("center", {})
    lat = element.get("lat", center.get("lat"))
    lng = element.get("lon", center.get("lon"))
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def in_bounds(element, bounds):
    if not bounds:
        return True
    coords = element_coordinates(element)
    if not coords:
        return False
    lat, lng = coords
    min_lat, max_lat, min_lng, max_lng = bounds
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


def collect_area_elements(district):
    elements = []
    seen_source_ids = set()
    for name in DISTRICT_ALIASES.get(district, [district]):
        data = fetch_overpass(overpass_area_query(name))
        for element in data.get("elements", []):
            source_id = f"{element.get('type')}/{element.get('id')}"
            if source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            elements.append(element)
    return elements


def collect_radius_elements(path, radius_m):
    center = district_center(path)
    if not center:
        return []
    data = fetch_overpass(overpass_radius_query(center[0], center[1], radius_m))
    return data.get("elements", [])


def normalize_elements(elements, district, bounds):
    records = []
    seen_record_ids = set()
    for element in elements:
        source_id = f"{element.get('type')}/{element.get('id')}"
        if source_id in seen_record_ids:
            continue
        seen_record_ids.add(source_id)
        if element.get("lat") is None and not element.get("center"):
            continue
        if not in_bounds(element, bounds):
            continue
        records.append(normalize_element(element, district, len(records) + 1))
    return records


def fetch_district(path, radius_m):
    district = path.stem
    bounds = district_bounds(path)
    elements = collect_area_elements(district)
    records = normalize_elements(elements, district, bounds)
    if not elements:
        records = normalize_elements(collect_radius_elements(path, radius_m), district, bounds)
    elif not records:
        records = normalize_elements(collect_radius_elements(path, radius_m), district, bounds)
    return records


def fetch_district_bbox(district, bbox):
    elements = fetch_overpass(overpass_bbox_query(*bbox)).get("elements", [])
    return normalize_elements(elements, district, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--district", help="Fetch only one district file stem")
    parser.add_argument("--replace", action="store_true", help="Overwrite showroom JSON files")
    parser.add_argument(
        "--out-dir",
        default=str(SHOWROOM_DIR / "_osm_verified"),
        help="Output directory when not using --replace",
    )
    parser.add_argument("--radius-m", type=int, default=60000)
    parser.add_argument("--bbox", help="south,west,north,east bounds to use instead of district area lookup")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    paths = [SHOWROOM_DIR / f"{args.district}.json"] if args.district else sorted(SHOWROOM_DIR.glob("*.json"))
    out_dir = SHOWROOM_DIR if args.replace else Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for path in paths:
        district = path.stem
        if district.startswith("_"):
            continue
        output_path = out_dir / path.name
        if args.resume and output_path.exists():
            print(f"{district}: skipped existing {output_path}")
            continue
        if args.bbox:
            records = fetch_district_bbox(
                district,
                [float(value.strip()) for value in args.bbox.split(",")],
            )
        else:
            records = fetch_district(path, args.radius_m)
        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"{district}: wrote {len(records)} OSM-verified showrooms to {output_path}")
        time.sleep(5)


if __name__ == "__main__":
    main()
