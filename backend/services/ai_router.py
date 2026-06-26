# backend/services/ai_router.py

import requests
import os

REVELA_AI_URL = os.getenv(
    "REVELA_AI_URL"
)

def ask_ai(
    prompt,
    domain=None,
    context=None
):

    payload = {

        "prompt": prompt,
        "domain": domain,
        "context": context
    }

    try:

        response = requests.post(
            REVELA_AI_URL,
            json=payload,
            timeout=30
        )

        if response.status_code == 429:

            return {
                "message":
                "AI is currently busy. Please try again shortly.",
                "fallback": True
            }

        response.raise_for_status()

        return response.json()

    except requests.exceptions.Timeout:

        return {
            "message":
            "AI request timed out.",
            "fallback": True
        }

    except Exception as e:

        return {
            "message": str(e),
            "fallback": True
        }