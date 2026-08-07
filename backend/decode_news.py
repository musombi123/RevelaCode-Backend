import json
import os

# ======================================================
# BASE DIRECTORY
# ======================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

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
    Guarantees every event has a consistent schema and
    removes None values that can crash decoding.
    """

    event["headline"] = event.get("headline") or ""
    event["description"] = event.get("description") or ""
    event["content"] = event.get("content") or ""
    event["author"] = event.get("author") or ""

    event["url"] = event.get("url") or ""
    event["publishedAt"] = event.get("publishedAt") or ""

    event["source"] = event.get("source") or ""
    event["source_id"] = event.get("source_id") or ""

    event["region"] = event.get("region") or "global"
    event["location"] = event.get("location") or {}

    event["categories"] = event.get("categories") or ["general"]

    event["matched_symbols"] = event.get("matched_symbols") or []
    event["matched_verses"] = event.get("matched_verses") or []

    event["media_type"] = event.get("media_type") or "article"

    event["urlToImage"] = event.get("urlToImage") or ""
    event["video_url"] = event.get("video_url") or ""

    media = event.get("media") or {}

    media["images"] = media.get("images") or []
    media["videos"] = media.get("videos") or []

    event["media"] = media

    if not event["urlToImage"] and media["images"]:
        event["urlToImage"] = media["images"][0]

    if not event["video_url"] and media["videos"]:
        event["video_url"] = media["videos"][0]
        event["media_type"] = "video"

    return event


# ======================================================
# DECODE EVENT
# ======================================================

def decode_event(event, symbols):

    event = normalize_event(event)

    matched_symbols = []
    matched_verses = []

    searchable_text = " ".join([
        event["headline"],
        event["description"],
        event["content"]
    ]).lower()

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

            if symbol_name and symbol_name not in matched_symbols:
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

    if not os.path.exists(input_path):
        print(f"❌ Missing file: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    symbols = load_symbols()

    decoded_events = []

    for event in events:
        try:
            decoded_events.append(
                decode_event(event, symbols)
            )
        except Exception as e:
            print(
                f"⚠️ Failed to decode event: "
                f"{event.get('headline','<unknown>')} ({e})"
            )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            decoded_events,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"✅ Decoded {len(decoded_events)} events")
    print(f"📁 Saved to {output_path}")


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
