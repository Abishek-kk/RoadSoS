"""
gemini_client.py - Gemini API Client
Integrates Google's Gemini LLM to power RAG Chat, Risk Scoring, and Emergency Extraction.
"""

import logging
import time
from collections.abc import Callable
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
MAX_CHAT_OUTPUT_TOKENS = 512


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


def generate_chat_response(
    prompt: str,
    context: str = "",
    system_instruction: str = "",
    on_token: Callable[[str], None] | None = None,
) -> str:
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

    started = time.perf_counter()
    used_stream = False
    try:
        full_prompt = ""
        if context:
            full_prompt += f"Context/Knowledge Base Reference:\n---\n{context}\n---\n\n"
        full_prompt += f"User Question: {prompt}"

        config = types.GenerateContentConfig(
            temperature=0.45,
            top_p=0.95,
            max_output_tokens=MAX_CHAT_OUTPUT_TOKENS,
            system_instruction=system_instruction or None,
        )
        response_text, used_stream = _generate_content_text(client, full_prompt, config, on_token=on_token)
        _last_generation_failure_at = 0.0
        _log_success_once()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Gemini chat call completed: %sms streamed=%s prompt_chars=%s output_chars=%s max_tokens=%s",
            elapsed_ms,
            used_stream,
            len(full_prompt),
            len(response_text or ""),
            MAX_CHAT_OUTPUT_TOKENS,
        )
        return response_text
    except Exception as e:
        _last_generation_failure_at = time.monotonic()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.error(
            "Gemini API request failed after %sms; RoadSoS will use the deterministic fallback. Error: %s",
            elapsed_ms,
            e,
            exc_info=True,
        )
        return "Error: Gemini API request failed."


def _generate_content_text(
    client: Any,
    full_prompt: str,
    config: Any,
    on_token: Callable[[str], None] | None = None,
) -> tuple[str, bool]:
    stream_fn = getattr(client.models, "generate_content_stream", None)
    if callable(stream_fn):
        chunks: list[str] = []
        for chunk in stream_fn(
            model=DEFAULT_MODEL,
            contents=full_prompt,
            config=config,
        ):
            text = getattr(chunk, "text", None)
            if text:
                chunks.append(text)
                if on_token:
                    on_token(text)
        streamed_text = "".join(chunks)
        if streamed_text.strip():
            return streamed_text, True

    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=full_prompt,
        config=config,
    )
    response_text = response.text or ""
    if on_token and response_text:
        on_token(response_text)
    return response_text, False
