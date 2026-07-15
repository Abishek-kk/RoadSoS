# RoadSOS Backend

Road safety and emergency SOS backend built with FastAPI.

## Project Structure

```
roadsos-backend/
├── app/                          — main application package
│   ├── main.py                   — FastAPI app entry point
│   ├── config.py                 — env vars, API keys, settings
│   ├── dependencies.py           — shared FastAPI dependencies
│   ├── routes/                   — core API routes
│   │   ├── location.py           — POST /api/location
│   │   ├── sos.py                — POST /api/sos
│   │   ├── hospitals.py          — GET /api/hospitals
│   │   ├── ambulances.py         — GET /api/ambulances
│   │   ├── police.py             — GET /api/police
│   │   ├── showrooms.py          — GET /api/showrooms
│   │   ├── puncture_shops.py     — GET /api/puncture-shops
│   │   ├── towing.py             — GET /api/towing
│   │   ├── chat.py               — POST /api/chat (RAG + Ollama/Gemini)
│   │   ├── alerts.py             — GET /api/alerts
│   │   ├── contacts.py           — GET/POST /api/contacts
│   │   ├── push.py               — GET/POST/DELETE /api/push
│   │   ├── risk.py               — GET /api/risk
│   │   └── route.py              — GET /api/route
│   ├── services/                 — core business logic
│   │   ├── danger_zone_service.py — geofencing + risk scoring
│   │   ├── sos_service.py        — SOS workflow + notifications
│   │   ├── notification_service.py — Firebase FCM + Twilio SMS
│   │   ├── location_service.py   — GPS processing + Haversine
│   │   └── route_service.py      — Dijkstra safe route calc
│   ├── ai/                       — AI layer
│   │   ├── rag_pipeline.py       — retrieval + context builder
│   │   ├── gemini_client.py      — Gemini API calls
│   │   ├── retrieval.py          — RAG ranking + filtering
│   │   ├── risk_scorer.py        — road danger scoring engine
│   │   └── rule_engine.py        — emergency action rules
│   ├── algorithms/               — algorithms
│   │   ├── haversine.py          — GPS distance calculation
│   │   ├── dijkstra.py           — safest route finder
│   │   └── geofencing.py         — radius boundary detection
│   └── models/                   — Pydantic schemas
│       ├── user.py               — user schema
│       ├── sos.py                — SOS event schema
│       ├── alert.py              — alert schema
│       └── location.py           — GPS payload schema
├── data/                         — knowledge base
│   ├── danger_zones.json         — blackspots + risk levels
│   ├── hospitals/                — district-wise hospital GPS + contacts
│   ├── police_stations/          — district-wise station GPS + contacts
│   ├── towing_services/          — district-wise towing GPS + contacts
│   ├── road_alerts.json          — active incidents
│   ├── emergency_guides.txt      — first-aid instructions
│   └── safety_rules.txt          — road safety rules
├── db/                           — database layer
│   ├── database.py               — SQLite/PostgreSQL connection
│   ├── models.py                 — SQLAlchemy ORM models
│   └── crud.py                   — DB read/write operations
├── requirements.txt              — all Python dependencies
├── .env                          — Gemini key, Firebase, Twilio
└── README.md
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure `.env` with your API keys.

3. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```

## Gemini Chat With Ollama Fallback

RoadSoS uses Gemini for `/api/chat` whenever `GEMINI_API_KEY` is configured.
Ollama is only used as a fallback if Gemini fails or no Gemini key is available.

1. Install Ollama and pull a chat model:
   ```bash
   ollama pull llama3.1:8b
   ```

2. Start Ollama if it is not already running:
   ```bash
   ollama serve
   ```
   On Windows and macOS, Ollama may already be running as a background service.

3. Keep these values in `roadsos-backend/.env` and restart the backend:
   ```env
   LLM_PROVIDER=gemini
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1:8b
   ```

If both Gemini and Ollama are stopped or unreachable, RoadSoS keeps serving chat
requests by using the deterministic fallback response builder.
