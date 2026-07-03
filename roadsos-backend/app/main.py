"""
RoadSoS — AI Powered Road Safety & Emergency Coordination System
FastAPI Application Entry Point
Team Accelerate | IIT Madras Road Safety Hackathon 2026
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import time

# --- Route imports ---
from app.routes import location, sos, hospitals, police, towing, chat, alerts, contacts, risk, route
from app.config import get_llm_provider, get_ollama_model

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("roadsos")

# -------------------------------------------------------------------
# App initialisation
# -------------------------------------------------------------------

app = FastAPI(
    title="RoadSoS API",
    description=(
        "AI-Powered Road Safety & Emergency Coordination System. "
        "Provides real-time danger zone alerts, one-tap SOS, "
        "RAG chatbot support, and emergency contact notifications."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Database Initialization ---
from db.database import init_db

@app.on_event("startup")
def startup_db_client():
    init_db()
    logger.info("Database initialized (all tables created).")

# -------------------------------------------------------------------
# Middleware
# -------------------------------------------------------------------

# CORS — allow React frontend (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # React dev server
        "http://localhost:5173",   # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "https://roadsos.app",     # Production domain (update as needed)
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing middleware — logs response time for every request
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Process-Time-Ms"] = str(process_time)
    logger.info(f"{request.method} {request.url.path} — {process_time}ms")
    return response

# -------------------------------------------------------------------
# Global exception handler
# -------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error. Please try again.",
        },
    )

# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------

app.include_router(
    location.router,
    prefix="/api",
    tags=["Location & Danger Zones"],
)

app.include_router(
    sos.router,
    prefix="/api",
    tags=["SOS & Emergency"],
)

app.include_router(
    hospitals.router,
    prefix="/api",
    tags=["Hospitals"],
)

app.include_router(
    police.router,
    prefix="/api",
    tags=["Police Stations"],
)

app.include_router(
    towing.router,
    prefix="/api",
    tags=["Towing Services"],
)

app.include_router(
    chat.router,
    prefix="/api",
    tags=["AI Chatbot"],
)

app.include_router(
    alerts.router,
    prefix="/api",
    tags=["Road Alerts"],
)

app.include_router(
    contacts.router,
    prefix="/api",
    tags=["Emergency Contacts"],
)

app.include_router(
    risk.router,
    prefix="/api",
    tags=["Risk Assessment"],
)

app.include_router(
    route.router,
    prefix="/api",
    tags=["Route Planning"],
)

# -------------------------------------------------------------------
# Health & root endpoints
# -------------------------------------------------------------------

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint — confirms API is running."""
    return {
        "app": "RoadSoS API",
        "version": "1.0.0",
        "status": "running",
        "message": "Preventing accidents before they happen. Saving lives when they do.",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    Used by cloud hosting (AWS/GCP) load balancers and monitoring tools.
    """
    return {
        "status": "healthy",
        "service": "RoadSoS Backend",
    }


@app.get("/api/status", tags=["Health"])
async def api_status():
    """
    Full API status — lists all active route modules.
    Useful for frontend to verify connectivity on app launch.
    """
    provider = get_llm_provider()
    model = get_ollama_model() if provider == "ollama" else "Google Gemini"
    return {
        "success": True,
        "routes": {
            "location":  "/api/location",
            "sos":       "/api/sos",
            "hospitals": "/api/hospitals",
            "police":    "/api/police",
            "towing":    "/api/towing",
            "chat":      "/api/chat",
            "alerts":    "/api/alerts",
            "contacts":  "/api/contacts",
            "risk":      "/api/risk",
            "route":     "/api/route",
        },
        "ai": {
            "provider": provider,
            "model":    model,
            "pipeline": "File-based RAG",
        },
    }

# -------------------------------------------------------------------
# Run directly (development only)
# Use: python app/main.py
# Production: uvicorn app.main:app --host 0.0.0.0 --port 8000
# -------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,       # Auto-reload on file changes (dev only)
        log_level="info",
    )
