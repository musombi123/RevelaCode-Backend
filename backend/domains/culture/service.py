# backend/domains/culture/service.py

from services.ai_router import ask_ai
from services.domain_registry import register_domain

def culture_handler(query, user_context=None):
    """
    Cultural & societal intelligence.
    Explains human behavior, trends, history, symbols, and movements.
    """

    prompt = f"""
    You are a cultural analyst and social historian.
    Analyze the topic below in a neutral, academic, and accessible way.

    Focus on:
    - Cultural context
    - Historical background
    - Social impact
    - Modern relevance
    - Global perspective

    Avoid religious framing unless explicitly requested.

    Topic:
    {query}
    """

    return ask_ai(
        prompt=prompt,
        domain="culture",
        context=user_context
    )

register_domain("culture", culture_handler)
