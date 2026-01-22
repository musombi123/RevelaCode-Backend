# backend/bible_decoder.py
import json
import os
import re
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SYMBOLS_FILE = os.path.join(os.path.dirname(__file__), "symbols_data.json")
try:
    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        SYMBOLS = json.load(f)
    logger.info("✅ Loaded symbols_data.json")
except Exception as e:
    logger.error(f"❌ Could not load symbols: {e}")
    SYMBOLS = {}

class BibleDecoder:
    def __init__(self, symbols=None):
        self.symbols = symbols or SYMBOLS

    def decode_verse(self, verse: str):
        """
        Returns a dict: {decoded: [...]}
        Each item: {symbol_name: symbol_details} or {message: ...}
        """
        verse_lower = (verse or "").lower()
        decoded = []

        for key, data in self.symbols.items():
            # Make sure it’s a dict with keywords
            if not isinstance(data, dict):
                continue

            keywords = data.get("keywords", [])
            # include the symbol name itself as a keyword
            search_terms = keywords + [key]

            for term in search_terms:
                pattern = r'\b' + re.escape(term.lower()) + r'\b'
                if re.search(pattern, verse_lower):
                    decoded.append({key: data})
                    break  # match each symbol only once

        if not decoded:
            decoded.append({"message": "⚠️ No symbolic meaning detected in this prophecy."})

        return {"decoded": decoded}

    def decode_text(self, verse: str):
        """Alias to match frontend call"""
        return self.decode_verse(verse)
