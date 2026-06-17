# backend/prophecy_notifications.py
from collections import Counter
from datetime import datetime
from backend.routes.notifications_routes import push_notification


def push_daily_prophecy_summary(events):
    if not events:
        return

    categories = Counter()

    for event in events:
        symbols = (
            event.get("matched_symbols")
            or event.get("categories")
            or []
        )

        for cat in symbols:
            categories[cat] += 1

    top = categories.most_common(5)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    text = (
        f"🔮 Daily Prophecy Update ({today})\n\n"
        f"Total Events: {len(events)}\n\n"
    )

    if top:
        text += "Top Signals:\n"
        for name, count in top:
            text += f"• {name}: {count}\n"
    else:
        text += "No major category signals detected today.\n"

    push_notification(
        text=text,
        extra={
            "type": "daily_prophecy_summary",
            "events_count": len(events),
            "top_categories": dict(top)
        }
    )