from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.ai import gemini_client, local_llm_client
from app.config import get_gemini_api_key


logger = logging.getLogger("roadsos.ai.llm_router")


@dataclass(frozen=True)
class GenerationResult:
    reply: str
    provider: str
    used_llm: bool
    error: str = ""


def generate(
    prompt: str,
    context: str,
    system_instruction: str,
    on_token: Callable[[str], None] | None = None,
) -> GenerationResult:
    """
    Generate with Gemini first, then the local Ollama LLM.

    Callers receive a structured failure instead of exceptions so routes never
    leak stack traces to users.
    """
    providers = []
    if get_gemini_api_key():
        providers.append(("gemini", gemini_client))
    else:
        logger.info("LLM selected: local fallback because Gemini key is missing")
    providers.append(("ollama", local_llm_client))

    last_error = ""
    for provider_name, client in providers:
        logger.info("LLM selected: %s", provider_name)
        try:
            if on_token:
                try:
                    reply = client.generate_chat_response(
                        prompt=prompt,
                        context=context,
                        system_instruction=system_instruction,
                        on_token=on_token,
                    )
                except TypeError:
                    reply = client.generate_chat_response(
                        prompt=prompt,
                        context=context,
                        system_instruction=system_instruction,
                    )
                    if is_successful_reply(reply):
                        on_token(reply)
            else:
                reply = client.generate_chat_response(
                    prompt=prompt,
                    context=context,
                    system_instruction=system_instruction,
                )
        except Exception as exc:
            logger.error("%s generation raised an exception: %s", provider_name, exc, exc_info=True)
            last_error = str(exc)
            continue

        if is_successful_reply(reply):
            logger.info("Generation completed with %s", provider_name)
            return GenerationResult(reply=reply.strip(), provider=provider_name, used_llm=True)
        last_error = reply or f"{provider_name} returned an empty response"
        logger.warning("%s generation failed: %s", provider_name, last_error[:300])

    return GenerationResult(
        reply="",
        provider="none",
        used_llm=False,
        error=last_error or "No LLM provider returned a usable response.",
    )


def is_successful_reply(reply: str | None) -> bool:
    if not reply:
        return False
    return not reply.strip().lower().startswith("error:")
