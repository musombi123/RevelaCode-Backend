import json
import os
import logging
from datetime import datetime

# === CONFIG ===
KEYWORDS = {
    "wars_conflicts": ["war", "conflict", "strike", "bomb", "attack", "missile"],
    "natural_disasters": ["earthquake", "flood", "wildfire", "eruption", "tsunami", "hurricane"],
    "economic": ["inflation", "recession", "crash", "unemployment", "foreclosure"],
    "crime": ["shooting", "murder", "serial killer", "rape", "abduction"],
    "politics": ["coup", "impeachment", "corruption", "resignation"],
    "health": ["outbreak", "virus", "pandemic", "epidemic", "ebola", "covid"],
    "social_morality": ["lgbt", "scandal", "hypocrisy", "child abuse", "drag queen", "abortion"]
}

EVENTS_DIR = "./events"
OUTPUT_DIR = "./events_tagged"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# === TAGGING ===
def categorize_article(event):
    headline = event.get("headline", "")
    description = event.get("description", "")
    text = f"{headline} {description}".lower()

    matched_categories = []

    for category, keywords in KEYWORDS.items():
        if any(word in text for word in keywords):
            matched_categories.append(category)

    return matched_categories if matched_categories else ["general"]

# === MAIN ===
def categorize_events_file(filename):
    input_path = os.path.join(EVENTS_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(input_path):
        logging.error(f"File not found: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    tagged_events = []
    for event in events:
        categories = categorize_article(event)
        event["categories"] = categories
        tagged_events.append(event)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tagged_events, f, indent=2, ensure_ascii=False)

    logging.info(f"✅ Tagged {len(tagged_events)} events → saved to {output_path}")

# === AUTO-RUN ===
if __name__ == "__main__":
    files = sorted(
        f for f in os.listdir(EVENTS_DIR)
        if f.startswith("events_") and f.endswith(".json")
    )

    if not files:
        logging.warning("⚠️ No events JSON files found in ./events. Run fetch_news.py first!")
    else:
        latest_file = files[-1]
        logging.info(f"🔍 Categorizing latest file: {latest_file}")
        categorize_events_file(latest_file)
