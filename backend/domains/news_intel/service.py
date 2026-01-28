from services.ai_router import ask_ai
from services.domain_registry import register_domain

def news_handler(query, user_context=None):
    prompt = f"""
    Decode current events, trends, and implications.
    Be neutral, factual, and forward-looking.

    Topic: {query}
    """

    return ask_ai(prompt, domain="news")

register_domain("news_intel", news_handler)
