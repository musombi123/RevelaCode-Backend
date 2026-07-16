import json
import os

# ======================================================
# BASE DIRECTORY
# ======================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

# ======================================================
# PATHS
# ======================================================

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

SYMBOLS_FILE = os.path.join(CURRENT_DIR, "symbols_keywords.json")

TAGGED_DIR = os.path.join(BASE_DIR, "events_tagged")
OUTPUT_DIR = os.path.join(BASE_DIR, "events_decoded")

# ======================================================
# LOAD SYMBOLS
# ======================================================

def load_symbols():
    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ======================================================
# NORMALIZE EVENT
# ======================================================

def normalize_event(event):
    """
    Guarantees every event has the same schema.
    """

    event.setdefault("headline", "")
    event.setdefault("description", "")
    event.setdefault("content", "")
    event.setdefault("author", "")

    event.setdefault("url", "")
    event.setdefault("publishedAt", "")

    event.setdefault("source", "")
    event.setdefault("source_id", "")

    event.setdefault("region", "global")
    event.setdefault("location", {})

    event.setdefault("categories", ["general"])

    event.setdefault("matched_symbols", [])
    event.setdefault("matched_verses", [])

    event.setdefault("media_type", "article")

    event.setdefault("urlToImage", "")
    event.setdefault("video_url", "")

    event.setdefault("media", {})
    event["media"].setdefault("images", [])
    event["media"].setdefault("videos", [])

    # Backward compatibility
    if (
        not event["urlToImage"]
        and event["media"]["images"]
    ):
        event["urlToImage"] = event["media"]["images"][0]

    if (
        not event["video_url"]
        and event["media"]["videos"]
    ):
        event["video_url"] = event["media"]["videos"][0]
        event["media_type"] = "video"

    return event

# ======================================================
# DECODE EVENT
# ======================================================

def decode_event(event, symbols):

    event = normalize_event(event)

    matched_symbols = []
    matched_verses = []

    searchable_text = (
        event["headline"] +
        " " +
        event["description"]
    ).lower()

    if not searchable_text.strip():

        event["matched_symbols"] = ["general"]
        event["matched_verses"] = []

        return event

    for symbol in symbols.get("symbols", []):

        symbol_name = (
            symbol.get("symbol", "")
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
        )

        keywords = symbol.get("keywords", [])
        verses = symbol.get("verses", [])

        if any(
            keyword.lower() in searchable_text
            for keyword in keywords
        ):

            if (
                symbol_name
                and symbol_name not in matched_symbols
            ):
                matched_symbols.append(symbol_name)

            for verse in verses:
                if verse not in matched_verses:
                    matched_verses.append(verse)

    if not matched_symbols:
        matched_symbols.append("general")

    event["matched_symbols"] = matched_symbols
    event["matched_verses"] = matched_verses

    print(
        f"[MATCH] {event['headline'][:70]} -> {matched_symbols}"
    )

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

    decoded_events = [
        decode_event(event, symbols)
        for event in events
    ]

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            decoded_events,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"✅ Decoded {len(decoded_events)} events"
    )

    print(
        f"📁 Saved to {output_path}"
    )

# ======================================================
# CLI
# ======================================================

if __name__ == "__main__":

    if not os.path.exists(TAGGED_DIR):
        print("🚫 events_tagged directory not found")
        exit(1)

    files = sorted(
        [
            f
            for f in os.listdir(TAGGED_DIR)
            if f.startswith("events_")
            and f.endswith(".json")
        ]
    )

    if not files:
        print(
            "🚫 No tagged events found. Run categorize.py first."
        )
        exit(0)

    latest = files[-1]

    decode_events_file(latest)