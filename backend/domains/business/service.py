# backend/domains/business/service.py

from services.ai_router import ask_ai
from services.domain_registry import register_domain

def business_handler(query, user_context=None):
    """
    Business, markets, innovation, and strategy intelligence.
    """

    prompt = f"""
    You are a business strategist and market analyst.
    Analyze the topic with a forward-thinking, practical mindset.

    Focus on:
    - Market trends
    - Opportunities and risks
    - Strategic insights
    - Innovation potential
    - Real-world application

    Be concise, actionable, and realistic.
    Avoid hype. Avoid religion.

    Topic:
    {query}
    """

    return ask_ai(
        prompt=prompt,
        domain="business",
        context=user_context
    )

register_domain("business", business_handler)
