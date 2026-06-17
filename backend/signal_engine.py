from backend.filter_prophecy_news import calculate_score
from backend.routes.notifications_routes import push_notification
from backend.bible_decoder import BibleDecoder

decoder = BibleDecoder()

KEYWORDS = {
    "wars_conflicts": ["war", "conflict", "strike", "bomb", "attack", "missile"],
    "economy": ["inflation", "recession", "crash"],
    "politics": ["election", "government", "president", "coup"],
}

IGNORE = ["sports", "music", "entertainment", "movie"]

def categorize(text):
    cats = []
    text = text.lower()

    for k, words in KEYWORDS.items():
        if any(w in text for w in words):
            cats.append(k)

    return cats or ["general"]


def enrich_event(event):
    text = " ".join([
        event.get("headline", ""),
        event.get("description", ""),
        event.get("content", "")
    ])

    # 1. SCORE
    score = calculate_score(text)
    event["prophecy_score"] = score

    # 2. CATEGORIES
    event["categories"] = categorize(text)

    # 3. BIBLE DECODER
    decoded = decoder.decode_verse(text).get("decoded", [])

    symbols = []
    verses = []

    for item in decoded:
        if isinstance(item, dict) and "message" not in item:
            symbol = list(item.keys())[0]
            symbols.append(symbol)
            ref = item[symbol].get("reference")
            if ref:
                verses.append(ref)

    event["matched_symbols"] = symbols
    event["matched_verses"] = verses

    return event


def process_event(event):
    event = enrich_event(event)

    # ALERT RULE
    if event["prophecy_score"] >= 8:
        push_notification(
            text=f"🚨 Prophecy Alert: {event.get('headline','')}",
            extra={
                "type": "prophecy_event",
                "score": event["prophecy_score"],
                "url": event.get("url"),
                "categories": event["categories"],
                "matched_symbols": event["matched_symbols"],
                "matched_verses": event["matched_verses"],
            }
        )

    return event