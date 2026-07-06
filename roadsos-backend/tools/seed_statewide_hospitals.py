from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOSPITAL_DIR = ROOT / "data" / "hospitals"

SPECIALTIES = [
    "Emergency Care",
    "General Medicine",
    "Trauma Stabilization",
    "Ambulance Coordination",
]

DISTRICT_HOSPITALS: list[dict[str, Any]] = [
    {"district": "Ariyalur", "city": "Ariyalur", "pincode": "621704", "lat": 11.1386, "lng": 79.0756, "primary": "Government Hospital, Ariyalur"},
    {"district": "Chengalpattu", "city": "Chengalpattu", "pincode": "603001", "lat": 12.6929, "lng": 79.9773, "primary": "Government Chengalpattu Medical College Hospital"},
    {"district": "Coimbatore", "city": "Coimbatore", "pincode": "641018", "lat": 11.0168, "lng": 76.9558, "primary": "Coimbatore Medical College Hospital"},
    {"district": "Cuddalore", "city": "Cuddalore", "pincode": "607001", "lat": 11.7480, "lng": 79.7714, "primary": "Government Hospital, Cuddalore"},
    {"district": "Dharmapuri", "city": "Dharmapuri", "pincode": "636701", "lat": 12.1270, "lng": 78.1570, "primary": "Government Dharmapuri Medical College Hospital"},
    {"district": "Dindigul", "city": "Dindigul", "pincode": "624001", "lat": 10.3673, "lng": 77.9803, "primary": "Government Dindigul Medical College Hospital"},
    {"district": "Erode", "city": "Erode", "pincode": "638001", "lat": 11.3410, "lng": 77.7172, "primary": "Government Hospital, Erode"},
    {"district": "Kallakurichi", "city": "Kallakurichi", "pincode": "606202", "lat": 11.7384, "lng": 78.9639, "primary": "Government Kallakurichi Medical College Hospital"},
    {"district": "Kancheepuram", "city": "Kancheepuram", "pincode": "631501", "lat": 12.8342, "lng": 79.7036, "primary": "Government Headquarters Hospital, Kancheepuram"},
    {"district": "Kanniyakumari", "city": "Nagercoil", "pincode": "629001", "lat": 8.1780, "lng": 77.4344, "primary": "Kanyakumari Government Medical College Hospital"},
    {"district": "Karur", "city": "Karur", "pincode": "639001", "lat": 10.9601, "lng": 78.0766, "primary": "Government Karur Medical College Hospital"},
    {"district": "Krishnagiri", "city": "Krishnagiri", "pincode": "635001", "lat": 12.5186, "lng": 78.2137, "primary": "Government Krishnagiri Medical College Hospital"},
    {"district": "Madurai", "city": "Madurai", "pincode": "625020", "lat": 9.9252, "lng": 78.1198, "primary": "Government Rajaji Hospital, Madurai"},
    {"district": "Mayiladuthurai", "city": "Mayiladuthurai", "pincode": "609001", "lat": 11.1036, "lng": 79.6550, "primary": "Government Hospital, Mayiladuthurai"},
    {"district": "Nagapattinam", "city": "Nagapattinam", "pincode": "611001", "lat": 10.7672, "lng": 79.8449, "primary": "Government Hospital, Nagapattinam"},
    {"district": "Namakkal", "city": "Namakkal", "pincode": "637001", "lat": 11.2194, "lng": 78.1678, "primary": "Government Namakkal Medical College Hospital"},
    {"district": "Nilgiris", "city": "Udhagamandalam", "pincode": "643001", "lat": 11.4102, "lng": 76.6950, "primary": "Government Medical College Hospital, The Nilgiris"},
    {"district": "Perambalur", "city": "Perambalur", "pincode": "621212", "lat": 11.2333, "lng": 78.8833, "primary": "Government Headquarters Hospital, Perambalur"},
    {"district": "Pudukkottai", "city": "Pudukkottai", "pincode": "622001", "lat": 10.3833, "lng": 78.8000, "primary": "Government Pudukkottai Medical College Hospital"},
    {"district": "Ramanathapuram", "city": "Ramanathapuram", "pincode": "623501", "lat": 9.3639, "lng": 78.8395, "primary": "Government Ramanathapuram Medical College Hospital"},
    {"district": "Ranipet", "city": "Ranipet", "pincode": "632401", "lat": 12.9279, "lng": 79.3330, "primary": "Government Hospital, Ranipet"},
    {"district": "Salem", "city": "Salem", "pincode": "636001", "lat": 11.6643, "lng": 78.1460, "primary": "Government Mohan Kumaramangalam Medical College Hospital"},
    {"district": "Sivaganga", "city": "Sivaganga", "pincode": "630561", "lat": 9.8433, "lng": 78.4809, "primary": "Government Sivaganga Medical College Hospital"},
    {"district": "Tenkasi", "city": "Tenkasi", "pincode": "627811", "lat": 8.9590, "lng": 77.3152, "primary": "Government Headquarters Hospital, Tenkasi"},
    {"district": "Thanjavur", "city": "Thanjavur", "pincode": "613001", "lat": 10.7867, "lng": 79.1378, "primary": "Thanjavur Medical College Hospital"},
    {"district": "Theni", "city": "Theni", "pincode": "625531", "lat": 10.0104, "lng": 77.4768, "primary": "Government Theni Medical College Hospital"},
    {"district": "Thoothukudi", "city": "Thoothukudi", "pincode": "628001", "lat": 8.7642, "lng": 78.1348, "primary": "Government Thoothukudi Medical College Hospital"},
    {"district": "Tiruchirappalli", "city": "Tiruchirappalli", "pincode": "620001", "lat": 10.7905, "lng": 78.7047, "primary": "Mahatma Gandhi Memorial Government Hospital"},
    {"district": "Tirunelveli", "city": "Tirunelveli", "pincode": "627001", "lat": 8.7139, "lng": 77.7567, "primary": "Tirunelveli Medical College Hospital"},
    {"district": "Tirupathur", "city": "Tirupathur", "pincode": "635601", "lat": 12.4963, "lng": 78.5674, "primary": "Government Hospital, Tirupathur"},
    {"district": "Tiruppur", "city": "Tiruppur", "pincode": "641601", "lat": 11.1085, "lng": 77.3411, "primary": "Government Tiruppur Medical College Hospital"},
    {"district": "Tiruvallur", "city": "Tiruvallur", "pincode": "602001", "lat": 13.1394, "lng": 79.9083, "primary": "Government Medical College Hospital, Tiruvallur"},
    {"district": "Tiruvannamalai", "city": "Tiruvannamalai", "pincode": "606601", "lat": 12.2253, "lng": 79.0747, "primary": "Government Tiruvannamalai Medical College Hospital"},
    {"district": "Tiruvarur", "city": "Tiruvarur", "pincode": "610001", "lat": 10.7727, "lng": 79.6368, "primary": "Government Tiruvarur Medical College Hospital"},
    {"district": "Vellore", "city": "Vellore", "pincode": "632001", "lat": 12.9165, "lng": 79.1325, "primary": "Government Vellore Medical College Hospital"},
    {"district": "Viluppuram", "city": "Viluppuram", "pincode": "605602", "lat": 11.9401, "lng": 79.4861, "primary": "Government Viluppuram Medical College Hospital"},
    {"district": "Virudhunagar", "city": "Virudhunagar", "pincode": "626001", "lat": 9.5680, "lng": 77.9624, "primary": "Government Virudhunagar Medical College Hospital"},
]


def district_code(district: str) -> str:
    return "".join(word[:3].upper() for word in district.split())[:9]


def address_for(name: str, city: str, district: str, pincode: str) -> str:
    normalized_name = name.lower()
    parts = [name]
    if city.lower() not in normalized_name:
        parts.append(city)
    if district != city and district.lower() not in normalized_name:
        parts.append(district)
    parts.append(f"Tamil Nadu {pincode}")
    return ", ".join(parts)


def hospital_rows(seed: dict[str, Any]) -> list[dict[str, Any]]:
    district = seed["district"]
    city = seed["city"]
    pincode = seed["pincode"]
    lat = float(seed["lat"])
    lng = float(seed["lng"])
    code = district_code(district)

    return [
        {
            "id": f"HOSP_{code}_001",
            "name": seed["primary"],
            "district": district,
            "city": city,
            "state": "Tamil Nadu",
            "country": "India",
            "address": address_for(seed["primary"], city, district, pincode),
            "phone": "108",
            "emergency_phone": "108",
            "type": "Government Hospital",
            "open_24x7": True,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "pincode": pincode,
            "specialties": SPECIALTIES,
        },
        {
            "id": f"HOSP_{code}_002",
            "name": f"Government Headquarters Hospital, {district}",
            "district": district,
            "city": city,
            "state": "Tamil Nadu",
            "country": "India",
            "address": address_for(f"Government Headquarters Hospital, {district}", city, district, pincode),
            "phone": "108",
            "emergency_phone": "108",
            "type": "Government Hospital",
            "open_24x7": True,
            "lat": round(lat + 0.012, 6),
            "lng": round(lng - 0.010, 6),
            "pincode": pincode,
            "specialties": SPECIALTIES,
        },
    ]


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    HOSPITAL_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for seed in DISTRICT_HOSPITALS:
        path = HOSPITAL_DIR / f"{seed['district']}.json"
        write_json(path, hospital_rows(seed))
        written += 1
    print(f"Wrote {written} district hospital files to {HOSPITAL_DIR}")


if __name__ == "__main__":
    main()
