from services.ai_router import ask_ai
from services.domain_registry import register_domain

def scholar_handler(query, user_context=None):
    prompt = f"""
    You are an academic research assistant.
    Analyze the following content objectively, cite reasoning,
    avoid religious framing unless requested.

    Query: {query}
    """

    return ask_ai(prompt, domain="scholar", context=user_context)

register_domain("scholar", scholar_handler)
