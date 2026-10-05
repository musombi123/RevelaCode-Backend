# backend/notifications_service.py

from backend.routes.notifications_routes import (
    load_notifications,
    push_notification,
)


def push_prophecy_event(
    event,
):
    """
    Create a prophecy notification safely.

    Invalid event payloads are ignored instead of
    crashing the daily pipeline.
    """

    if not isinstance(
        event,
        dict,
    ):
        return None

    headline = str(
        event.get(
            "headline",
            "",
        )
        or ""
    ).strip()

    url = str(
        event.get(
            "url",
            "",
        )
        or ""
    ).strip()

    notifications = load_notifications()

    # -----------------------------------------------------
    # Duplicate detection
    # -----------------------------------------------------

    already_exists = False

    for notification in notifications:

        if not isinstance(
            notification,
            dict,
        ):
            continue

        existing_url = str(
            notification.get(
                "url",
                "",
            )
            or ""
        ).strip()

        if (
            url
            and existing_url
            and existing_url == url
        ):
            already_exists = True
            break

    if already_exists:
        return None

    # -----------------------------------------------------
    # Push
    # -----------------------------------------------------

    return push_notification(
        text=(
            f"🚨 Prophecy Alert: "
            f"{headline}"
        ),
        extra={
            "type": "prophecy_event",
            "score": event.get(
                "prophecy_score",
                event.get(
                    "score",
                    0,
                ),
            ),
            "url": url,
            "headline": headline,
            "source": event.get(
                "source",
                "",
            ),
            "publishedAt": event.get(
                "publishedAt",
                "",
            ),
            "categories": event.get(
                "categories",
                [],
            ),
            "matched_symbols": event.get(
                "matched_symbols",
                [],
            ),
            "matched_verses": event.get(
                "matched_verses",
                [],
            ),
        },
    )
