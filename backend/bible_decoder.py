import json
import os
import re

# === Load symbols_data.json ===
filepath = os.path.join(os.path.dirname(__file__), 'symbols_data.json')
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        SYMBOLS = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"[ERROR] Failed to load prophecy symbols: {e}")
    SYMBOLS = {}

# === Decode a verse against symbol definitions ===
def decode_verse(verse):
    if not SYMBOLS:
        return {"error": "❌ Symbolic data could not be loaded."}

    decoded_parts = []
    verse_lower = verse.lower()

    for symbol, details in SYMBOLS.items():
        if not isinstance(details, dict):
            continue

        keywords = details.get("keywords", [])
        search_terms = keywords + [symbol]

        for keyword in search_terms:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, verse_lower):
                decoded_parts.append({symbol: details})
                break  # Stop after first match per symbol

    return {
        "decoded": decoded_parts if decoded_parts else [
            {"message": "⚠️ No symbolic meaning detected in this prophecy."}
        ]
    }
