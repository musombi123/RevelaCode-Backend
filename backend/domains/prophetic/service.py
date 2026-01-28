# backend/domains/prophetic/service.py

from services.ai_router import ask_ai
from services.domain_registry import register_domain

def prophetic_handler(query, user_context=None):
    """
    Prophetic and symbolic interpretation.
    Multi-faith aware, not Christian-only.
    """

    prompt = f"""
    You are a symbolic and prophetic analyst.
    Interpret the input using:
    - Symbolism
    - Prophetic literature
    - Historical prophecy patterns
    - Cross-text references when relevant

    Be careful:
    - Do not assert beliefs as facts
    - Present interpretations, not conclusions
    - Respect multiple traditions and viewpoints

    Input:
    {query}
    """

    return ask_ai(
        prompt=prompt,
        domain="prophetic",
        context=user_context
    )

register_domain("prophetic", prophetic_handler)
