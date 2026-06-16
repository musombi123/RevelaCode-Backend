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
            "headline": headline,
            "score": event.get("prophecy_score", 0),
            "url": event.get("url", ""),
            "categories": event.get("matched_symbols", []),
            "source": event.get("source", ""),
            "publishedAt": event.get("publishedAt", "")
        }
    )