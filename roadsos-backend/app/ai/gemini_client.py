"""
gemini_client.py — Gemini API Client
Integrates Google's Gemini LLM to power RAG Chat, Risk Scoring, and Emergency Extraction.
"""

import logging
import google.generativeai as genai
from app.config import get_gemini_api_key

logger = logging.getLogger("roadsos.gemini")
_configured_key = ""


DEFAULT_MODEL = "gemini-1.5-flash"


def configure_gemini() -> bool:
    global _configured_key

    api_key = get_gemini_api_key()
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. Gemini API calls will fail.")
        return False

    if api_key != _configured_key:
        genai.configure(api_key=api_key)
        _configured_key = api_key
        logger.info("Gemini API client initialized successfully.")

    return True

def generate_chat_response(prompt: str, context: str = "", system_instruction: str = "") -> str:
    """
    Generates a response using Gemini for RAG or general chatbot queries.
    
    Args:
        prompt: The user query or current question.
        context: Retrieved documents or safety knowledge base content.
        system_instruction: Guidelines for the model's persona/behavior.
    """
    if not configure_gemini():
        return "Error: Gemini API key is missing. Please check your configuration."
        
    try:
        # Construct the generation config
        generation_config = {
            "temperature": 0.3,
            "top_p": 0.95,
            "max_output_tokens": 1024,
        }

        # Build full prompt containing context if available
        full_prompt = ""
        if context:
            full_prompt += f"Context/Knowledge Base Reference:\n---\n{context}\n---\n\n"
        full_prompt += f"User Question: {prompt}"

        # Initialize the model with system instruction if provided
        model = genai.GenerativeModel(
            model_name=DEFAULT_MODEL,
            generation_config=generation_config,
            system_instruction=system_instruction or None
        )

        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}", exc_info=True)
        return "Error: Gemini API request failed."

def get_risk_assessment(location_description: str, coordinates: dict, recent_alerts: list) -> str:
    """
    Leverages Gemini to assess the danger risk of a specific road coordinates/location.
    """
    if not configure_gemini():
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
        model = genai.GenerativeModel(
            model_name=DEFAULT_MODEL,
            system_instruction=system_instruction
        )
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        logger.error(f"Error getting risk assessment: {e}", exc_info=True)
        return '{"risk_level": "Unknown", "score": 0, "summary": "Failed to assess risk due to system error.", "safety_tips": []}'
