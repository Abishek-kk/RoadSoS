import json
from pathlib import Path


SHOWROOM_DIR = Path(__file__).resolve().parents[1] / "data" / "Showrooms"
FIELD_ORDER = [
    "id",
    "name",
    "district",
    "city",
    "state",
    "address",
    "phone",
    "emergency_phone",
    "type",
    "open_24x7",
    "lat",
    "lng",
    "pincode",
    "zone",
]


def extract_objects(text, filename):
    text = (
        text.replace("Use code with caution.", "")
        .replace("```json", "")
        .replace("```", "")
        .replace('\nname":', '\n"name":')
        .replace('\naddress":', '\n"address":')
    )
    objects = []
    depth = 0
    start = None
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                snippet = text[start : index + 1]
                try:
                    objects.append(json.loads(snippet))
                except json.JSONDecodeError as exc:
                    preview = snippet[max(0, exc.pos - 120) : exc.pos + 120]
                    raise ValueError(
                        f"{filename}: invalid object near char {exc.pos}: {preview!r}"
                    ) from exc
                start = None

    return objects, depth != 0


def normalize_record(record):
    normalized = {}
    for field in FIELD_ORDER:
        if field not in record:
            continue

        value = record[field]
        if field == "open_24x7":
            if isinstance(value, str):
                value = value.strip().lower() == "true"
            else:
                value = bool(value)
        elif field in {"lat", "lng"} and value not in (None, ""):
            value = float(value)
        elif field in {"phone", "emergency_phone", "pincode"} and value is not None:
            value = str(value).strip()
        elif isinstance(value, str):
            value = value.strip()

        normalized[field] = value

    for field, value in record.items():
        if field not in normalized:
            normalized[field] = value

    return normalized


def main():
    summary = []
    for path in sorted(SHOWROOM_DIR.glob("*.json")):
        records, skipped_fragment = extract_objects(
            path.read_text(encoding="utf-8"), path.name
        )
        normalized = [normalize_record(record) for record in records]
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        missing_phone = sum(not record.get("phone") for record in normalized)
        summary.append((path.name, len(normalized), missing_phone, skipped_fragment))

    for filename, count, missing_phone, skipped_fragment in summary:
        suffix = ", skipped dangling fragment" if skipped_fragment else ""
        print(f"{filename}: {count} records, {missing_phone} missing phone{suffix}")


if __name__ == "__main__":
    main()
