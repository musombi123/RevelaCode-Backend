# backend/prophecy_notifications.py
from collections import Counter
from backend.routes.notifications_routes import push_notification


def push_daily_prophecy_summary(events):
    if not events:
        return

    categories = Counter()

    for event in events:
        for cat in event.get("matched_symbols", []):
            categories[cat] += 1

    top = categories.most_common(5)

    text = (
        f"🔮 Daily Prophecy Update\n\n"
        f"{len(events)} prophetic events detected today.\n\n"
    )

    for name, count in top:
        text += f"• {name}: {count}\n"

    push_notification(
        text=text,
        extra={
            "type": "daily_prophecy_summary",
            "events_count": len(events)
        }
    )