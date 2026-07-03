"""
local_llm_client.py - Ollama API Client
Runs RoadSoS chat generation against a local Ollama model.
"""

import logging
from typing import Any

import httpx

from app.config import get_ollama_base_url, get_ollama_model


logger = logging.getLogger("roadsos.ollama")
REQUEST_TIMEOUT_SECONDS = 20.0


def generate_chat_response(prompt: str, context: str = "", system_instruction: str = "") -> str:
    """
    Generates a response using a local Ollama model for RAG or general chatbot queries.
    Returns the reply text, or a string starting with "Error:" on failure.
    """
    base_url = get_ollama_base_url().rstrip("/")
    model = get_ollama_model()
    if not base_url:
        return "Error: Ollama base URL is missing. Please check your configuration."
    if not model:
        return "Error: Ollama model is missing. Please check your configuration."

    messages: list[dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": _build_user_message(prompt, context)})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    try:
        response = httpx.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        content = (data.get("message") or {}).get("content", "")
        if not content:
            logger.error("Ollama returned an empty chat response for model %s.", model)
            return "Error: Ollama returned an empty response."
        return content
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama API request failed with status %s; RoadSoS will use the deterministic fallback. Error: %s",
            exc.response.status_code,
            exc.response.text[:500],
            exc_info=True,
        )
        return "Error: Ollama API request failed."
    except httpx.HTTPError as exc:
        logger.error(
            "Ollama API request failed; RoadSoS will use the deterministic fallback. Error: %s",
            exc,
            exc_info=True,
        )
        return "Error: Ollama API request failed."
    except Exception as exc:
        logger.error(
            "Ollama response parsing failed; RoadSoS will use the deterministic fallback. Error: %s",
            exc,
            exc_info=True,
        )
        return "Error: Ollama API request failed."


def _build_user_message(prompt: str, context: str = "") -> str:
    full_prompt = ""
    if context:
        full_prompt += f"Context/Knowledge Base Reference:\n---\n{context}\n---\n\n"
    full_prompt += f"User Question: {prompt}"
    return full_prompt
