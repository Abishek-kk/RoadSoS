# config.py — env vars, API keys, settings
import os
from dotenv import dotenv_values, load_dotenv

load_dotenv()

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
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "roadsos_jwt_super_secret_signing_key_2026")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "roadsos_internal_secret_key")
    DATA_DIR = os.getenv("DATA_DIR", "data")


settings = Settings()


def get_gemini_api_key() -> str:
    """Return the active Gemini key without requiring a backend restart after .env edits."""
    return os.getenv("GEMINI_API_KEY") or (dotenv_values().get("GEMINI_API_KEY") or "")


def get_env_value(name: str) -> str:
    return os.getenv(name) or (dotenv_values().get(name) or "")
