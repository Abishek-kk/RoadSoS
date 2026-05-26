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
│   │   ├── police.py             — GET /api/police
│   │   ├── towing.py             — GET /api/towing
│   │   ├── chat.py               — POST /api/chat (RAG + Gemini)
│   │   ├── alerts.py             — GET /api/alerts
│   │   └── contacts.py           — POST /api/contacts
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
│   ├── hospitals.json            — hospital GPS + contacts
│   ├── police_stations.json      — station GPS + contacts
│   ├── towing.json               — towing GPS + contacts
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
