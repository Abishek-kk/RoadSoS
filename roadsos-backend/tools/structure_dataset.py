from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STRUCTURED_DIR = DATA_DIR / "structured"


def read_json_lenient(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = clean_concatenated_arrays(text)
        return json.loads(cleaned)


def clean_concatenated_arrays(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\s*\[\]\s*\[", "[", cleaned)
    cleaned = re.sub(r"\]\s*\[", ",", cleaned)
    cleaned = re.sub(r",\s*\[\s*(?=\{)", ",\n", cleaned)
    return cleaned


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def repair_source_json_files() -> list[str]:
    repaired: list[str] = []
    for path in sorted((DATA_DIR / "police_stations").glob("*.json")):
        original = path.read_text(encoding="utf-8")
        try:
            json.loads(original)
            continue
        except json.JSONDecodeError:
            pass

        rows = read_json_lenient(path)
        if not isinstance(rows, list):
            raise ValueError(f"{path} did not parse to a list")
        write_json(path, rows)
        repaired.append(path.relative_to(DATA_DIR).as_posix())
    return repaired


def normalize_police_station_row(
    row: dict[str, Any],
    district_hint: str,
) -> dict[str, Any]:
    location = location_from_row(row)
    district = row.get("district") or district_hint
    city = row.get("city") or district
    name = row.get("name") or row.get("station_name")
    pincode = row.get("pincode")

    address_parts = [part for part in (name, city, district, "Tamil Nadu", pincode) if part]
    address = row.get("address") or ", ".join(dict.fromkeys(address_parts))

    normalized: dict[str, Any] = {
        "id": row.get("id"),
        "name": name,
        "district": district,
        "city": city,
        "state": row.get("state") or "Tamil Nadu",
        "address": address,
        "phone": row.get("phone"),
        "emergency_phone": row.get("emergency_phone") or "100",
        "type": row.get("type") or "Police Station",
        "open_24x7": row.get("open_24x7", True),
        "lat": location["lat"],
        "lng": location["lng"],
    }

    for key in ("pincode", "zone", "jurisdiction", "officer", "officer_in_charge"):
        if row.get(key) is not None:
            normalized[key] = row[key]

    return normalized


def structure_police_source_files() -> list[str]:
    structured: list[str] = []
    for path in sorted((DATA_DIR / "police_stations").glob("*.json")):
        rows = read_json_lenient(path)
        if not isinstance(rows, list):
            raise ValueError(f"{path} did not parse to a list")

        normalized_rows = [
            normalize_police_station_row(row, path.stem)
            for row in rows
            if isinstance(row, dict)
        ]
        write_json(path, normalized_rows)
        structured.append(path.relative_to(DATA_DIR).as_posix())
    return structured


def parse_safety_rules() -> list[dict[str, Any]]:
    text = (DATA_DIR / "safety_rules.txt").read_text(encoding="utf-8")
    sections: list[dict[str, Any]] = []

    for part in re.split(r"(?m)(?=^=== SECTION \d+:)", text):
        match = re.search(r"=== SECTION (\d+):\s*(.*?)\s*===", part)
        if not match:
            continue

        rules = []
        for rule_match in re.finditer(r"(?m)^(\d+)\.\s+(.*)$", part):
            rules.append(
                {
                    "rule_no": int(rule_match.group(1)),
                    "text": rule_match.group(2).strip(),
                }
            )

        sections.append(
            {
                "id": f"SAFETY_SECTION_{int(match.group(1)):02d}",
                "record_type": "safety_rule_section",
                "title": match.group(2).strip(),
                "source_file": "safety_rules.txt",
                "items": rules,
            }
        )

    return sections


def parse_emergency_guides() -> list[dict[str, Any]]:
    text = (DATA_DIR / "emergency_guides.txt").read_text(encoding="utf-8")
    guides: list[dict[str, Any]] = []

    for part in re.split(r"\n(?=GUIDE \d+:)", text):
        match = re.search(r"GUIDE (\d+):\s*(.*?)\n=+", part)
        if not match:
            continue

        lines = [
            line.strip()
            for line in part.splitlines()
            if line.strip() and not set(line.strip()) <= {"="}
        ]
        body = "\n".join(lines[1:])

        guides.append(
            {
                "id": f"EMERGENCY_GUIDE_{int(match.group(1)):02d}",
                "record_type": "emergency_guide",
                "title": match.group(2).strip(),
                "source_file": "emergency_guides.txt",
                "content": body,
            }
        )

    return guides


def location_from_row(row: dict[str, Any]) -> dict[str, float | None]:
    lat = row.get("lat", row.get("latitude"))
    lng = row.get("lng", row.get("longitude"))

    if (lat is None or lng is None) and row.get("location_link"):
        match = re.search(
            r"[?&]q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
            str(row["location_link"]),
        )
        if match:
            lat = float(match.group(1))
            lng = float(match.group(2))

    return {"lat": lat, "lng": lng}


def service_record(
    row: dict[str, Any],
    category: str,
    source_file: str,
    district_hint: str | None = None,
) -> dict[str, Any]:
    location = location_from_row(row)
    district = row.get("district") or row.get("city") or district_hint
    city = row.get("city") or district
    name = row.get("name") or row.get("station_name")

    return {
        "id": row.get("id"),
        "record_type": "emergency_service",
        "category": category,
        "name": name,
        "service_type": row.get("type") or ("Police Station" if category == "police" else None),
        "district": district,
        "city": city,
        "state": row.get("state") or "Tamil Nadu",
        "address": row.get("address"),
        "phone": row.get("phone") or row.get("emergency_phone"),
        "pincode": row.get("pincode"),
        "open_24x7": row.get("open_24x7"),
        "rating": row.get("rating"),
        "location": location,
        "source_file": source_file,
        "metadata": {
            key: row.get(key)
            for key in ("jurisdiction", "zone", "officer", "specialties", "services")
            if row.get(key) is not None
        },
    }


def build_services() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for path in sorted((DATA_DIR / "hospitals").glob("*.json")):
        for row in read_json_lenient(path):
            records.append(
                service_record(row, "hospital", path.relative_to(DATA_DIR).as_posix(), path.stem)
            )

    for path in sorted((DATA_DIR / "police_stations").glob("*.json")):
        for row in read_json_lenient(path):
            records.append(
                service_record(row, "police", path.relative_to(DATA_DIR).as_posix(), path.stem)
            )

    for path in sorted((DATA_DIR / "towing_services").glob("*.json")):
        payload = read_json_lenient(path)
        rows = payload.get("services", []) if isinstance(payload, dict) else payload
        for row in rows:
            records.append(
                service_record(row, "towing", path.relative_to(DATA_DIR).as_posix(), row.get("district"))
            )

    return records


def build_alerts() -> dict[str, Any]:
    alerts = read_json_lenient(DATA_DIR / "road_alerts.json")
    return {
        "metadata": {
            "title": "RoadSoS Road Alerts",
            "source_file": "road_alerts.json",
            "record_count": len(alerts),
        },
        "records": alerts,
    }


def build_danger_zones() -> dict[str, Any]:
    zones = read_json_lenient(DATA_DIR / "danger_zones.json")
    return {
        "metadata": {
            "title": "RoadSoS Danger Zones",
            "source_file": "danger_zones.json",
            "record_count": len(zones),
        },
        "records": zones,
    }


def build_police_stations(services: list[dict[str, Any]]) -> dict[str, Any]:
    records = [record for record in services if record["category"] == "police"]
    return {
        "metadata": {
            "title": "RoadSoS Police Stations",
            "record_count": len(records),
            "state": "Tamil Nadu",
            "source_root": "police_stations",
        },
        "records": records,
    }


def dataset_manifest(
    repaired_files: list[str],
    structured_police_files: list[str],
    services: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
) -> dict[str, Any]:
    service_counts: dict[str, int] = {}
    for record in services:
        service_counts[record["category"]] = service_counts.get(record["category"], 0) + 1

    return {
        "dataset": "RoadSoS local safety and emergency dataset",
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": "roadsos-backend/data",
        "structured_root": "roadsos-backend/data/structured",
        "repaired_source_files": repaired_files,
        "structured_police_source_files": structured_police_files,
        "collections": {
            "knowledge_base": {
                "path": "structured/knowledge_base.json",
                "records": len(knowledge),
                "types": ["safety_rule_section", "emergency_guide"],
            },
            "emergency_services": {
                "path": "structured/emergency_services.json",
                "records": len(services),
                "counts_by_category": service_counts,
            },
            "police_stations": {
                "path": "structured/police_stations.json",
                "records": service_counts.get("police", 0),
            },
            "road_alerts": {
                "path": "structured/road_alerts.json",
                "records": len(read_json_lenient(DATA_DIR / "road_alerts.json")),
            },
            "danger_zones": {
                "path": "structured/danger_zones.json",
                "records": len(read_json_lenient(DATA_DIR / "danger_zones.json")),
            },
        },
        "common_service_schema": [
            "id",
            "record_type",
            "category",
            "name",
            "service_type",
            "district",
            "city",
            "state",
            "address",
            "phone",
            "pincode",
            "open_24x7",
            "rating",
            "location.lat",
            "location.lng",
            "source_file",
            "metadata",
        ],
    }


def main() -> None:
    repaired_files = repair_source_json_files()
    structured_police_files = structure_police_source_files()
    knowledge = parse_safety_rules() + parse_emergency_guides()
    services = build_services()

    write_json(
        STRUCTURED_DIR / "knowledge_base.json",
        {
            "metadata": {
                "title": "RoadSoS Safety Knowledge Base",
                "record_count": len(knowledge),
                "source_files": ["safety_rules.txt", "emergency_guides.txt"],
            },
            "records": knowledge,
        },
    )
    write_json(
        STRUCTURED_DIR / "emergency_services.json",
        {
            "metadata": {
                "title": "RoadSoS Emergency Services",
                "record_count": len(services),
            },
            "records": services,
        },
    )
    write_json(STRUCTURED_DIR / "police_stations.json", build_police_stations(services))
    write_json(STRUCTURED_DIR / "road_alerts.json", build_alerts())
    write_json(STRUCTURED_DIR / "danger_zones.json", build_danger_zones())
    write_json(
        STRUCTURED_DIR / "manifest.json",
        dataset_manifest(repaired_files, structured_police_files, services, knowledge),
    )

    print(f"Structured dataset written to {STRUCTURED_DIR}")
    print(f"Repaired source files: {len(repaired_files)}")
    print(f"Structured police source files: {len(structured_police_files)}")
    print(f"Knowledge records: {len(knowledge)}")
    print(f"Emergency service records: {len(services)}")


if __name__ == "__main__":
    main()
