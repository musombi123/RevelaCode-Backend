import json
import os
import re


# Load symbol data once at startup
filepath = os.path.join(os.path.dirname(__file__), 'symbols_data.json')
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        SYMBOLS = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"[ERROR] Failed to load symbols: {e}")
    SYMBOLS = {}

def decode_verse(verse):
    if not SYMBOLS:
        return {"error": "Symbol data could not be loaded."}

    decoded_parts = []
    verse_lower = verse.lower()

    for symbol, meaning in SYMBOLS.items():
        if re.search(r'\b' + re.escape(symbol.lower()) + r'\b', verse_lower):
            decoded_parts.append({symbol: meaning})

    return {"decoded": decoded_parts or "No symbolic content found."}
