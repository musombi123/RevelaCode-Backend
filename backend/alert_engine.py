import json
import logging
import os
from hashlib import sha256

from backend.filter_prophecy_news import calculate_score
from backend.notifier import send_alert


logger = logging.getLogger(__name__)


# =========================================================
# LOCAL CACHE
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SEEN_FILE = os.path.join(
    BASE_DIR,
    "seen_events.json",
)


# =========================================================
# EVENT ID
# =========================================================

def get_event_id(event):
    """
    Create a stable ID even when an event has no URL.
    """

    url = str(
        event.get("url") or ""
    ).strip()

    if url:
        return url

    headline = str(
        event.get("headline") or ""
    ).strip()

    description = str(
        event.get("description") or ""
    ).strip()

    raw = (
        f"{headline}|{description}"
    )

    return sha256(
        raw.encode("utf-8")
    ).hexdigest()


# =========================================================
# LOAD SEEN
# =========================================================

def load_seen():

    if not os.path.exists(
        SEEN_FILE
    ):
        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if not isinstance(
            data,
            list,
        ):
            return set()

        return set(
            str(item)
            for item in data
            if item
        )

    except Exception as exc:

        logger.warning(
            "Failed to load seen events: %s",
            exc,
        )

        return set()


# =========================================================
# SAVE SEEN
# =========================================================

def save_seen(seen):

    try:

        with open(
            SEEN_FILE,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                sorted(seen),
                f,
                ensure_ascii=False,
                indent=2,
            )

    except Exception as exc:

        logger.error(
            "Failed to save seen events: %s",
            exc,
        )


# =========================================================
# PROCESS EVENTS
# =========================================================

def process_events(events):

    if not events:
        return []

    seen = load_seen()

    alerted = []

    for event in events:

        if not isinstance(
            event,
            dict,
        ):
            continue

        event_id = get_event_id(
            event
        )

        if event_id in seen:
            continue

        headline = str(
            event.get("headline")
            or ""
        ).strip()

        description = str(
            event.get("description")
            or ""
        ).strip()

        text = (
            f"{headline} "
            f"{description}"
        ).strip()

        if not text:
            seen.add(event_id)
            continue

        try:

            score = calculate_score(
                text
            )

            event["score"] = score

        except Exception as exc:

            logger.exception(
                "Failed to score event: %s",
                exc,
            )

            continue

        logger.info(
            "📰 Event score=%s | %s",
            score,
            headline[:120],
        )

        # -------------------------------------------------
        # ALERT
        # -------------------------------------------------

        if score >= 8:

            try:

                send_alert(
                    event
                )

                alerted.append(
                    event
                )

                logger.info(
                    "🚨 Alert sent: %s",
                    headline[:120],
                )

            except Exception as exc:

                logger.exception(
                    "Failed to send alert: %s",
                    exc,
                )

                # Do NOT mark it seen if
                # notification failed.
                continue

        # -------------------------------------------------
        # MARK PROCESSED
        # -------------------------------------------------

        seen.add(
            event_id
        )

    save_seen(
        seen
    )

    return alerted
