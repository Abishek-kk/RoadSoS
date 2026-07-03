# config.py — env vars, API keys, settings
import os
from dotenv import dotenv_values, load_dotenv
from pathlib import Path

DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=DOTENV_PATH, override=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./roadsos.db")

# App Settings
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "")


# Settings Object Pattern
class Settings:
    GEMINI_API_KEY = GEMINI_API_KEY
    FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS
    TWILIO_ACCOUNT_SID = TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN = TWILIO_AUTH_TOKEN
    TWILIO_PHONE_NUMBER = TWILIO_PHONE_NUMBER
    TWILIO_WHATSAPP_NUMBER = TWILIO_WHATSAPP_NUMBER
    DATABASE_URL = DATABASE_URL
    DEBUG = DEBUG
    LLM_PROVIDER = LLM_PROVIDER
    OLLAMA_BASE_URL = OLLAMA_BASE_URL
    OLLAMA_MODEL = OLLAMA_MODEL
    OSRM_BASE_URL = OSRM_BASE_URL
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "roadsos_jwt_super_secret_signing_key_2026")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "roadsos_internal_secret_key")
    DATA_DIR = os.getenv("DATA_DIR", "data")


settings = Settings()


def get_gemini_api_key() -> str:
    """Return the active Gemini key without requiring a backend restart after .env edits."""
    return os.getenv("GEMINI_API_KEY") or (dotenv_values(dotenv_path=DOTENV_PATH).get("GEMINI_API_KEY") or "")


def get_env_value(name: str) -> str:
    return os.getenv(name) or (dotenv_values(dotenv_path=DOTENV_PATH).get(name) or "")


def _get_live_env_value(name: str, default: str = "") -> str:
    return dotenv_values(dotenv_path=DOTENV_PATH).get(name) or os.getenv(name) or default


def get_llm_provider() -> str:
    """Return the active chat LLM provider without requiring a backend restart."""
    return (_get_live_env_value("LLM_PROVIDER", LLM_PROVIDER) or "gemini").strip().lower()


def get_ollama_base_url() -> str:
    """Return the active Ollama base URL without requiring a backend restart."""
    return (_get_live_env_value("OLLAMA_BASE_URL", OLLAMA_BASE_URL) or "http://localhost:11434").strip()


def get_ollama_model() -> str:
    """Return the active Ollama model without requiring a backend restart."""
    return (_get_live_env_value("OLLAMA_MODEL", OLLAMA_MODEL) or "llama3.1:8b").strip()


def get_osrm_base_url() -> str:
    """Return an optional OSRM base URL used for route geometry."""
    return (_get_live_env_value("OSRM_BASE_URL", OSRM_BASE_URL) or "").strip().rstrip("/")
