import json
import os

# ======================================================
# BASE DIRECTORY (backend/)
# ======================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================================================
# PATHS (ALL INSIDE /backend)
# ======================================================

SYMBOLS_FILE = os.path.join(BASE_DIR, "symbols_keywords.json")
TAGGED_DIR = os.path.join(BASE_DIR, "events_tagged")
OUTPUT_DIR = os.path.join(BASE_DIR, "events_decoded")

# ======================================================
# LOAD SYMBOLS
# ======================================================

def load_symbols():
    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ======================================================
# DECODE LOGIC
# ======================================================

def decode_event(event, symbols):
    # Skip if already decoded
    if "matched_symbols" in event:
        return event

    matched_verses = []
    matched_symbols = []

    headline = (event.get("headline") or "") + " " + (event.get("description") or "")
    headline = headline.lower()

    for symbol in symbols.get("symbols", []):
        symbol_name = (
            symbol.get("symbol", "")
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
        )

        keywords = symbol.get("keywords", [])
        verses = symbol.get("verses", [])

        if any(kw.lower() in headline for kw in keywords):
            if symbol_name and symbol_name not in matched_symbols:
                matched_symbols.append(symbol_name)

            for verse in verses:
                if verse not in matched_verses:
                    matched_verses.append(verse)

    if not matched_symbols:
        matched_symbols = ["general"]

    event["matched_symbols"] = matched_symbols
    event["matched_verses"] = matched_verses

    print(f"[MATCH] {headline[:60]} → {matched_symbols}")
    return event

# ======================================================
# FILE PROCESSING
# ======================================================

def decode_events_file(filename):
    input_path = os.path.join(TAGGED_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, filename)

    with open(input_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    symbols = load_symbols()
    decoded_events = [decode_event(event, symbols) for event in events]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(decoded_events, f, indent=2, ensure_ascii=False)

    print(f"✅ Decoded {len(decoded_events)} events → saved to {output_path}")

# ======================================================
# CLI ENTRY
# ======================================================

if __name__ == "__main__":
    if not os.path.exists(TAGGED_DIR):
        print("🚫 events_tagged directory not found")
        exit(1)

    files = [
        f for f in os.listdir(TAGGED_DIR)
        if f.startswith("events_") and f.endswith(".json")
    ]

    if not files:
        print("🚫 No tagged events JSON files found. Run categorize.py first!")
    else:
        latest_file = sorted(files)[-1]
        decode_events_file(latest_file)
