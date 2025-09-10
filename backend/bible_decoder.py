import json
import os
import re
import logging

# === Setup logging ===
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# === Load symbols_data.json ===
filepath = os.path.join(os.path.dirname(__file__), 'symbols_data.json')
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        SYMBOLS = json.load(f)
    logger.info("Loaded prophecy symbols successfully.")
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error(f"Failed to load prophecy symbols: {e}")
    SYMBOLS = {}


class BibleDecoder:
    def __init__(self, symbols: dict = None):
        self.symbols = symbols or SYMBOLS

    def decode_verse(self, verse: str):
        """
        Decode a verse against symbol definitions.
        """
        if not self.symbols:
            return {"error": "❌ Symbolic data could not be loaded."}

        decoded_parts = []
        verse_lower = verse.lower()

        for symbol, details in self.symbols.items():
            if not isinstance(details, dict):
                continue

            keywords = details.get("keywords", [])
            search_terms = keywords + [symbol]

            for keyword in search_terms:
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, verse_lower):
                    decoded_parts.append({symbol: details})
                    break

        return {
            "decoded": decoded_parts if decoded_parts else [
                {"message": "⚠️ No symbolic meaning detected in this prophecy."}
            ]
        }
