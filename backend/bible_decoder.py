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

    def normalize_text(self, text: str):
        """
        Lowercase and strip punctuation for reliable matching.
        """
        text = (text or "").lower()
        # Remove punctuation except digits and letters
        text = re.sub(r"[^\w\s]", " ", text)
        # Collapse multiple spaces
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def decode_verse(self, verse: str):
        """
        Returns a dict with all symbols detected in the verse.
        """
        verse_normalized = self.normalize_text(verse)
        decoded = []

        for key, data in self.symbols.items():
            if not isinstance(data, dict):
                continue

            keywords = data.get("keywords", [])
            # include the symbol itself as a keyword
            search_terms = keywords + [key]

            for term in search_terms:
                term_norm = self.normalize_text(term)
                # Use relaxed boundaries for numbers, strict for words
                if term_norm.replace(" ", "").isdigit():
                    pattern = re.escape(term_norm)
                else:
                    pattern = r"\b" + re.escape(term_norm) + r"\b"

                if re.search(pattern, verse_normalized):
                    decoded.append({key: data})
                    break  # only one match per symbol

        if not decoded:
            decoded.append({"message": "⚠️ No symbolic meaning detected in this prophecy."})

        return {"decoded": decoded}

    def decode_text(self, verse: str):
        """
        Alias to match frontend call
        """
        return self.decode_verse(verse)
