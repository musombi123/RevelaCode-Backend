# backend/services/ai_router.py

import requests
import os

REVELA_AI_URL = os.getenv("REVELA_AI_URL")

def ask_ai(prompt, domain=None, context=None):
    payload = {
        "prompt": prompt,
        "domain": domain,
        "context": context
    }

    response = requests.post(REVELA_AI_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()
