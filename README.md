# RoadSoS

AI-powered road safety and emergency coordination system .

RoadSoS helps users monitor nearby danger zones, trigger SOS alerts, find emergency services, and get concise AI safety guidance during road incidents.

## Features

- Live road safety dashboard with current location and active monitoring.
- Nearby emergency services:
  - Hospitals
  - Police stations
  - Towing services
- One-tap SOS workflow with emergency contact notification support.
- Road alerts and danger-zone data for accident-prone areas.
- AI assistant powered by a file-based RAG pipeline and Google Gemini.
- Location-aware sorting using Haversine distance.
- Emergency guidance knowledge base for first aid and road safety rules.
- Responsive React frontend with dashboard, alerts, chat, contacts, hospitals, police, and towing pages.

## Tech Stack

Frontend:
- React 19
- TypeScript
- Vite
- TanStack Router / TanStack Start
- Tailwind CSS
- shadcn/ui-style components
- lucide-react icons

Backend:
- FastAPI
- Python
- SQLAlchemy
- SQLite
- Pydantic
- Google Gemini API
- Firebase Admin / Twilio-ready notification layer
- OpenStreetMap Nominatim lookup for nearby amenities

## Project Structure

```text
team_accalerate/
  roadsos-backend/
    app/
      main.py                  FastAPI app entry point
      routes/
        location.py            POST /api/location
        sos.py                 POST /api/sos
        hospitals.py           GET /api/hospitals
        police.py              GET /api/police
        towing.py              GET /api/towing
        alerts.py              GET /api/alerts
        chat.py                POST /api/chat
        contacts.py            GET/POST /api/contacts
        _data.py               shared JSON, distance, OSM helpers
      ai/                      Gemini and RAG helpers
      models/                  Pydantic schemas
      services/                SOS, notification, routing, risk services
    data/
      danger_zones.json
      hospitals/
      police_stations/
      towing_services/
      road_alerts.json
      emergency_guides.txt
      safety_rules.txt
    db/
      database.py
      models.py
      crud.py
    requirements.txt
    README.md

  roadsos-frontend/
    src/
      components/
      lib/
        api.ts                 API client and fallback mock data
        location.ts            browser/saved location helpers
      routes/
        index.tsx              dashboard
        alerts.tsx
        chat.tsx
        contacts.tsx
        hospitals.tsx
        police.tsx
        towing.tsx
        __root.tsx
    package.json
    vite.config.ts
```

## Getting Started

### Prerequisites

Install:
- Python 3.10 or newer
- Node.js 20 or newer
- npm

### Backend Setup

```bash
cd roadsos-backend
pip install -r requirements.txt
```

Create a `.env` file in `roadsos-backend/`:

```env
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=sqlite:///./roadsos.db

# Optional notification credentials
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
FIREBASE_CREDENTIALS_PATH=
```

Run the backend:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend URLs:
- API root: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

### Frontend Setup

```bash
cd roadsos-frontend
npm install
```

Optional `.env` file in `roadsos-frontend/`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Run the frontend:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173
```

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/health` | Backend health check |
| GET | `/api/status` | API route status |
| POST | `/api/location` | Submit or update current location |
| POST | `/api/sos` | Trigger SOS workflow |
| GET | `/api/hospitals?lat=&lng=` | List nearby hospitals |
| GET | `/api/police?lat=&lng=` | List nearby police stations |
| GET | `/api/towing?lat=&lng=` | List nearby towing services |
| GET | `/api/alerts?lat=&lng=` | List nearby road alerts |
| GET | `/api/contacts` | List emergency contacts |
| POST | `/api/contacts` | Add emergency contact |
| POST | `/api/chat` | Ask RoadSoS AI assistant |

Example:

```bash
curl "http://127.0.0.1:8000/api/towing?lat=13.0827&lng=80.2707"
```

## Data Files

The backend uses local files in `roadsos-backend/data/` as the knowledge base:

- `danger_zones.json`: accident-prone blackspots and risk data.
- `road_alerts.json`: active or sample traffic and road incident alerts.
- `hospitals/`: district-wise hospital locations and contacts.
- `police_stations/`: district-wise police station locations and contacts.
- `towing_services/`: district-wise towing and roadside recovery services.
- `emergency_guides.txt`: first-aid and emergency response instructions.
- `safety_rules.txt`: road safety rules and legal guidance.

## AI Assistant

The chat endpoint builds context from:
- emergency guides
- safety rules
- road alerts
- hospitals
- police stations
- towing services

If `GEMINI_API_KEY` is configured, the backend sends the retrieved context to Gemini. If not, it falls back to a local rule-based response.

## Useful Commands

Backend:

```bash
cd roadsos-backend
python -m py_compile app/main.py app/routes/*.py
uvicorn app.main:app --reload
```

Frontend:

```bash
cd roadsos-frontend
npm run dev
npm run build
npm run lint
```

## Notes

- Emergency phone defaults are used when a local record does not include a phone number:
  - hospitals: `108`
  - police: `100`
  - towing: `112`
- The frontend includes fallback mock data so pages remain usable if the backend is temporarily unavailable.
- Location-aware lists are sorted by distance when `lat` and `lng` query parameters are provided.

## Team

Team Accelerate  
