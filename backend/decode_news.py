import json
import os

SYMBOLS_FILE = "symbols_keywords.json"
TAGGED_DIR = "./events_tagged"
OUTPUT_DIR = "./events_decoded"

def load_symbols():
    with open(SYMBOLS_FILE, "r") as f:
        return json.load(f)

def decode_event(event, symbols):
    matched_verses = []
    headline = (event.get("headline") or "") + " " + (event.get("description") or "")
    headline = headline.lower()
    for symbol in symbols.get("symbols", []):
        keywords = symbol.get("keywords", [])
        for word in keywords:
            if word.lower() in headline:
                verses = symbol.get("verses", [])
                for verse in verses:
                    if verse not in matched_verses:
                        matched_verses.append(verse)
    event["matched_verses"] = matched_verses
    return event

def decode_events_file(filename):
    input_path = os.path.join(TAGGED_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, filename)
    with open(input_path, "r", encoding="utf-8") as f:
        events = json.load(f)
    symbols = load_symbols()
    decoded_events = [decode_event(event, symbols) for event in events]
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(decoded_events, f, indent=2)
    print(f"Decoded {len(decoded_events)} events → saved to {output_path}")

if __name__ == "__main__":
    files = os.listdir(TAGGED_DIR)
    files = [f for f in files if f.startswith("events_") and f.endswith(".json")]
    if not files:
        print("No tagged events JSON files found. Run categorize.py first!")
    else:
        latest_file = sorted(files)[-1]
        decode_events_file(latest_file)