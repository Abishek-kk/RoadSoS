from __future__ import annotations

from app.services.context_builder import ContextPackage
from app.services.memory import ConversationTurn, format_history
from app.services.query_classifier import QueryProfile


SYSTEM_PROMPT = """
You are RoadSoS AI, a concise road-safety and emergency assistant.

Grounding rules:
- Every factual answer must be based only on RETRIEVED CONTEXT, LIVE CONTEXT,
  LOCATION SERVICES, EMERGENCY WORKFLOW CONTEXT, or conversation history.
- Do not invent phone numbers, distances, addresses, routes, laws, hospitals,
  police stations, towing services, danger zones, or service availability.
- If the retrieved context does not contain a reliable answer, say exactly:
  "I couldn't find reliable information in my knowledge base."
- If the user asks for nearest services or danger zones and coordinates are
  unavailable, ask them to share or allow location. Do not guess a place.
- For emergencies, put the most urgent emergency number or nearest verified
  service first, then give short safety steps.
- If context contains saved emergency contacts, mention them only when relevant
  to emergency help or contact requests.

Response style:
- Be practical, calm, and brief.
- Prefer bullets for steps and nearby-service lists.
- Keep most answers under 220 words unless the user asks for detail.
""".strip()


def build_prompt(
    profile: QueryProfile,
    context_package: ContextPackage,
    history: list[ConversationTurn],
) -> tuple[str, str, str]:
    """Return (system_prompt, context, user_prompt) for the LLM router."""
    history_block = format_history(history)
    user_prompt_parts = []
    if history_block:
        user_prompt_parts.append("CONVERSATION HISTORY (last 10 exchanges)\n" + history_block)
    user_prompt_parts.append("USER QUESTION\n" + profile.clean_question)
    if profile.retrieval_query != profile.clean_question:
        user_prompt_parts.append("RETRIEVAL QUERY\n" + profile.retrieval_query)
    user_prompt = "\n\n".join(user_prompt_parts)
    return SYSTEM_PROMPT, context_package.context, user_prompt
