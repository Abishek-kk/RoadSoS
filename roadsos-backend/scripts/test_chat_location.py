import requests
import json

url = "http://127.0.0.1:8000/api/chat"
payload = {
    "messages": [{"role": "user", "content": "what is my current location"}],
    "lat": 9.9252,
    "lng": 78.1198
}

r = requests.post(url, json=payload, timeout=30)
print(r.status_code)
try:
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except Exception:
    print(r.text)
