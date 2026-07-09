import json
from pathlib import Path


SHOWROOM_DIR = Path(__file__).resolve().parents[1] / "data" / "Showrooms"

FAKE_NAME_TERMS = {
    "bugatti",
    "rimac",
    "lucid",
    "fisker",
    "hopium",
    "zenvo",
    "faraday future",
    "polestar",
    "mclaren",
    "maserati",
    "hypercar",
    "hypercars",
}


ENCODING_REPAIRS = {
    "â€“": "-",
    "â€”": "-",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "CitroÃ«n": "Citroen",
    "La Maison CitroÃ«n": "La Maison Citroen",
}


def repair_text(value):
    if not isinstance(value, str):
        return value
    for broken, fixed in ENCODING_REPAIRS.items():
        value = value.replace(broken, fixed)
    return value


def normalize_key(value):
    return " ".join(repair_text(value).lower().split())


def is_fake_name(name):
    lowered = name.lower()
    return any(term in lowered for term in FAKE_NAME_TERMS)


def main():
    total_removed_duplicates = 0
    total_removed_fake = 0

    for path in sorted(SHOWROOM_DIR.glob("*.json")):
        records = json.loads(path.read_text(encoding="utf-8"))
        seen_ids = set()
        seen_name_addresses = set()
        cleaned = []
        removed_duplicates = 0
        removed_fake = 0
        repaired_encoding = 0

        for record in records:
            original_record = dict(record)
            for field in ("name", "address", "city", "district", "state", "zone"):
                if field in record:
                    record[field] = repair_text(record[field])
            if record != original_record:
                repaired_encoding += 1

            record_id = record.get("id")
            if record_id in seen_ids:
                removed_duplicates += 1
                continue
            seen_ids.add(record_id)

            name_address_key = (
                normalize_key(record.get("name", "")),
                normalize_key(record.get("address", "")),
            )
            if all(name_address_key) and name_address_key in seen_name_addresses:
                removed_duplicates += 1
                continue
            seen_name_addresses.add(name_address_key)

            if is_fake_name(record.get("name", "")):
                removed_fake += 1
                continue

            cleaned.append(record)

        if cleaned != records:
            path.write_text(
                json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        total_removed_duplicates += removed_duplicates
        total_removed_fake += removed_fake

        if removed_duplicates or removed_fake or repaired_encoding:
            print(
                f"{path.name}: removed {removed_duplicates} duplicate IDs, "
                f"{removed_fake} fake-looking records, "
                f"repaired {repaired_encoding} encoding issues"
            )

    print(f"Total duplicate IDs removed: {total_removed_duplicates}")
    print(f"Total fake-looking records removed: {total_removed_fake}")


if __name__ == "__main__":
    main()
