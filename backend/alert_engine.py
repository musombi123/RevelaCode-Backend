import time
import json
import os
from backend.filter_prophecy_news import calculate_score
from backend.notifier import send_alert

SEEN_FILE = "seen_events.json"

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def process_events(events):
    seen = load_seen()

    for event in events:
        url = event.get("url")

        if url in seen:
            continue

        text = event.get("headline", "") + " " + event.get("description", "")
        s = calculate_score(text)

        event["score"] = s

        # 🔥 ALERT THRESHOLD
        if s >= 8:
            send_alert(event)

        seen.add(url)

    save_seen(seen)