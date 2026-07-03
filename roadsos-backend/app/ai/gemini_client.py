"""
gemini_client.py - Gemini API Client
Integrates Google's Gemini LLM to power RAG Chat, Risk Scoring, and Emergency Extraction.
"""

import logging
import time
from typing import Any

from app.config import get_gemini_api_key

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logger = logging.getLogger("roadsos.gemini")
_configured_key = ""
_client: Any | None = None
_success_logged = False
_fallback_logged = False
_last_generation_failure_at = 0.0


DEFAULT_MODEL = "gemini-2.5-flash"
GENERATION_FAILURE_COOLDOWN_SECONDS = 60


def configure_gemini() -> Any | None:
    global _client, _configured_key, _fallback_logged

    api_key = get_gemini_api_key()
    if genai is None:
        if not _fallback_logged:
            logger.warning(
                "google-genai SDK is not installed. Gemini calls will fall back to "
                "the deterministic RoadSoS responder until requirements are installed."
            )
            _fallback_logged = True
        return None

    if not api_key:
        if not _fallback_logged:
            logger.warning(
                "GEMINI_API_KEY is not set. Gemini calls will fall back to the "
                "deterministic RoadSoS responder."
            )
            _fallback_logged = True
        return None

    if api_key != _configured_key or _client is None:
        _client = genai.Client(api_key=api_key)
        _configured_key = api_key
        logger.info("Gemini API client initialized for model %s.", DEFAULT_MODEL)

    return _client


def _log_success_once() -> None:
    global _success_logged
    if not _success_logged:
        logger.info("Gemini API calls are succeeding with model %s.", DEFAULT_MODEL)
        _success_logged = True


def generate_chat_response(prompt: str, context: str = "", system_instruction: str = "") -> str:
    """
    Generates a response using Gemini for RAG or general chatbot queries.

    Args:
        prompt: The user query or current question.
        context: Retrieved documents or safety knowledge base content.
        system_instruction: Guidelines for the model's persona/behavior.
    """
    global _last_generation_failure_at

    if (
        _last_generation_failure_at
        and time.monotonic() - _last_generation_failure_at < GENERATION_FAILURE_COOLDOWN_SECONDS
    ):
        return "Error: Gemini is temporarily unavailable."

    client = configure_gemini()
    if client is None:
        return "Error: Gemini API key is missing. Please check your configuration."

    try:
        full_prompt = ""
        if context:
            full_prompt += f"Context/Knowledge Base Reference:\n---\n{context}\n---\n\n"
        full_prompt += f"User Question: {prompt}"

        config = types.GenerateContentConfig(
            temperature=0.45,
            top_p=0.95,
            max_output_tokens=1400,
            system_instruction=system_instruction or None,
        )
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=full_prompt,
            config=config,
        )
        _last_generation_failure_at = 0.0
        _log_success_once()
        return response.text
    except Exception as e:
        _last_generation_failure_at = time.monotonic()
        logger.error(
            "Gemini API request failed; RoadSoS will use the deterministic fallback. Error: %s",
            e,
            exc_info=True,
        )
        return "Error: Gemini API request failed."


def get_risk_assessment(location_description: str, coordinates: dict, recent_alerts: list) -> str:
    """
    Leverages Gemini to assess the danger risk of a specific road coordinates/location.
    """
    client = configure_gemini()
    if client is None:
        return "Unable to perform risk assessment: API key missing."

    system_instruction = (
        "You are an expert road safety analyst. Assess the risk level (Low, Medium, High) "
        "and provide actionable safety recommendations based on the provided location context."
    )

    prompt = f"""
    Assess road safety for:
    Location Name/Description: {location_description}
    GPS Coordinates: {coordinates}
    Recent local alerts: {recent_alerts}

    Format response as a JSON string with key fields: 'risk_level' (Low/Medium/High), 'score' (0-100), 'summary' and 'safety_tips'.
    """

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            ),
        )
        _log_success_once()
        return response.text
    except Exception as e:
        logger.error(
            "Gemini risk assessment failed; returning unknown risk fallback. Error: %s",
            e,
            exc_info=True,
        )
        return '{"risk_level": "Unknown", "score": 0, "summary": "Failed to assess risk due to system error.", "safety_tips": []}'
