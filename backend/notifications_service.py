from backend.routes.notifications_routes import (
    push_notification,
    load_notifications
)

def push_prophecy_event(event):
    headline = event.get("headline") or ""

    notifications = load_notifications()

    already_exists = any(
        n.get("url") == event.get("url")
        for n in notifications
    )

    if already_exists:
        return

    push_notification(
        text=f"🚨 Prophecy Alert: {headline}",
        extra={
            "type": "prophecy_event",
            "score": event.get("prophecy_score", event.get("score", 0)),
            "url": event.get("url", ""),
            "headline": event.get("headline", ""),
            "source": event.get("source", ""),
            "publishedAt": event.get("publishedAt", ""),
            "categories": event.get("categories", []),
            "matched_symbols": event.get("matched_symbols", []),
            "matched_verses": event.get("matched_verses", [])
        }
    )