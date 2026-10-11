
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

from backend.filter_prophecy_news import filter_prophetic_events

# ======================================================
# CONFIGURATION
# ======================================================

RUN_HOUR = 2
CHECK_INTERVAL = 60
DRY_RUN = False

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)

LOCK_FILE = os.path.join(
    BACKEND_DIR,
    ".daily_runner.lock",
)

DECODED_DIR = os.path.join(
    BASE_DIR,
    "events_decoded",
)

# Use the same Python interpreter that started this runner.
commands = [
    [sys.executable, "-m", "backend.fetch_news"],
    [sys.executable, "-m", "backend.filter_prophecy_news"],
    [sys.executable, "-m", "backend.categorize"],
    [sys.executable, "-m", "backend.decode_news"],
    [sys.executable, "-m", "backend.archive_old_events"],
]

EVENT_WRAPPER_KEYS = (
    "events",
    "articles",
    "items",
    "results",
)

EVENT_FIELDS = {
    "headline",
    "title",
    "url",
    "link",
    "description",
}

# ======================================================
# LOGGING
# ======================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("daily_runner")


# ======================================================
# NORMALIZE EVENT DATA
# ======================================================

def normalize_events(
    payload: Any,
    source: str = "event payload",
) -> list[dict]:
    """
    Normalize supported JSON payloads into a list of dictionaries.

    Supports:
      - A list of event dictionaries.
      - A single event dictionary.
      - Wrapped payloads such as {"events": [...]}.
      - Dictionaries keyed by event ID.
      - JSON-encoded strings containing valid JSON.

    Invalid records are skipped with diagnostics rather than
    causing an unhandled '.get()' AttributeError.
    """

    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Ignoring string instead of event object in %s: %r",
                source,
                payload[:200],
            )
            return []

        if isinstance(decoded, str):
            logger.warning(
                "Ignoring nested string payload in %s",
                source,
            )
            return []

        return normalize_events(
            decoded,
            source=f"{source} (decoded JSON)",
        )

    if isinstance(payload, dict):
        # Recognize an individual event before looking for wrappers.
        if EVENT_FIELDS.intersection(payload.keys()):
            candidates = [payload]
        else:
            wrapper_found = False
            candidates = []

            for key in EVENT_WRAPPER_KEYS:
                if key in payload:
                    wrapper_found = True
                    return normalize_events(
                        payload[key],
                        source=f"{source}.{key}",
                    )

            if not wrapper_found:
                # Some feeds store records in a dictionary keyed by ID.
                if payload and all(
                    isinstance(value, dict)
                    for value in payload.values()
                ):
                    candidates = list(payload.values())
                else:
                    logger.warning(
                        "Unrecognized event JSON structure in %s; "
                        "top-level keys=%s",
                        source,
                        list(payload.keys())[:20],
                    )
                    return []

    elif isinstance(payload, (list, tuple)):
        candidates = list(payload)

    else:
        logger.warning(
            "Expected event list/object in %s, received %s",
            source,
            type(payload).__name__,
        )
        return []

    valid_events = []
    rejected = 0

    for index, item in enumerate(candidates):
        if isinstance(item, dict):
            valid_events.append(item)
        else:
            rejected += 1
            logger.warning(
                "Skipping invalid event: source=%s index=%s type=%s value=%r",
                source,
                index,
                type(item).__name__,
                str(item)[:160],
            )

    if rejected:
        logger.warning(
            "Rejected %s invalid record(s) from %s",
            rejected,
            source,
        )

    return valid_events


# ======================================================
# LOCKING
# ======================================================

def acquire_lock() -> bool:
    """Acquire the runner lock without overwriting an existing lock."""

    try:
        descriptor = os.open(
            LOCK_FILE,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )

        with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
            lock.write(str(os.getpid()))

        return True

    except FileExistsError:
        return False

    except OSError:
        logger.exception("Could not acquire daily runner lock")
        return False


def release_lock() -> None:
    try:
        if not os.path.exists(LOCK_FILE):
            return

        # Avoid removing a lock that now belongs to another process.
        with open(LOCK_FILE, "r", encoding="utf-8") as lock:
            owner = lock.read().strip()

        if owner == str(os.getpid()):
            os.remove(LOCK_FILE)

    except OSError:
        logger.exception("Could not release daily runner lock")


# ======================================================
# DAILY NEWS PIPELINE
# ======================================================

def run_pipeline() -> bool:
    logger.info("Starting daily news pipeline")

    # --------------------------------------------------
    # 1. Fetch, filter, categorize, decode and archive
    # --------------------------------------------------

    for command in commands:
        display_command = " ".join(
            f'"{part}"' if " " in part else part
            for part in command
        )

        logger.info("Running: %s", display_command)

        if DRY_RUN:
            logger.info("DRY RUN: execution skipped")
            continue

        try:
            result = subprocess.run(
                command,
                cwd=BASE_DIR,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        except OSError:
            logger.exception(
                "Could not start command: %s",
                display_command,
            )
            return False

        if result.stdout:
            logger.debug(
                "%s stdout:\n%s",
                display_command,
                result.stdout[-5000:],
            )

        if result.returncode != 0:
            logger.error(
                "Command failed with exit code %s: %s",
                result.returncode,
                display_command,
            )

            if result.stderr:
                logger.error(
                    "Command stderr:\n%s",
                    result.stderr[-10000:],
                )

            return False

        logger.info("Completed: %s", display_command)

    # --------------------------------------------------
    # 2. Load and validate decoded events
    # --------------------------------------------------

    stage = "locating decoded events"

    try:
        if not os.path.isdir(DECODED_DIR):
            logger.warning(
                "Decoded events directory does not exist: %s",
                DECODED_DIR,
            )
            return False

        files = sorted(
            filename
            for filename in os.listdir(DECODED_DIR)
            if filename.lower().endswith(".json")
            and os.path.isfile(
                os.path.join(DECODED_DIR, filename)
            )
        )

        if not files:
            logger.warning(
                "No decoded JSON event files found in %s",
                DECODED_DIR,
            )
            return False

        latest_file = files[-1]
        latest_path = os.path.join(
            DECODED_DIR,
            latest_file,
        )

        logger.info(
            "Loading decoded event file: %s",
            latest_file,
        )

        stage = "reading decoded JSON"

        with open(
            latest_path,
            "r",
            encoding="utf-8",
        ) as file:
            raw_events = json.load(file)

        events = normalize_events(
            raw_events,
            source=latest_file,
        )

        logger.info(
            "Valid decoded events: %s",
            len(events),
        )

        if not events:
            logger.warning(
                "No valid events to process from %s",
                latest_file,
            )
            return True

        # --------------------------------------------------
        # 3. Filter prophetic events
        # --------------------------------------------------

        stage = "filtering prophetic events"

        filtered_result = filter_prophetic_events(events)

        # The filter might return malformed records or a wrapper.
        filtered = normalize_events(
            filtered_result,
            source="filter_prophetic_events result",
        )

        logger.info(
            "Filtered prophetic events: %s",
            len(filtered),
        )

        # --------------------------------------------------
        # 4. Push high-scoring prophecy notifications
        # --------------------------------------------------

        stage = "sending prophecy notifications"

        from backend.notifications_service import push_prophecy_event

        sent_candidates = 0

        for event in filtered:
            raw_score = event.get("prophecy_score", 0)

            try:
                prophecy_score = float(raw_score or 0)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid prophecy_score=%r for event=%r",
                    raw_score,
                    str(event.get("headline") or event.get("title") or "")[:120],
                )
                continue

            if prophecy_score >= 10:
                push_prophecy_event(event)
                sent_candidates += 1

        logger.info(
            "Prophecy notification candidates processed: %s",
            sent_candidates,
        )

        # --------------------------------------------------
        # 5. Run the alert engine
        # --------------------------------------------------

        stage = "running alert engine"

        from backend.alert_engine import process_events

        alerted = process_events(filtered)

        logger.info(
            "Alert engine completed; alerts returned: %s",
            len(alerted) if isinstance(alerted, (list, tuple)) else "unknown",
        )

        # --------------------------------------------------
        # 6. Send the daily summary
        # --------------------------------------------------

        stage = "sending daily prophecy summary"

        from backend.prophecy_notifications import (
            push_daily_prophecy_summary,
        )

        push_daily_prophecy_summary(filtered)

        logger.info("Alert pipeline completed successfully")
        return True

    except Exception:
        logger.exception(
            "Alert pipeline failed during stage: %s",
            stage,
        )
        return False


# ======================================================
# SCHEDULER LOOP
# ======================================================

def scheduler_loop() -> None:
    logger.info("Daily runner scheduler started")

    last_run_date = None

    while True:
        now = datetime.now()

        if (
            now.hour == RUN_HOUR
            and last_run_date != now.date()
        ):
            if not acquire_lock():
                logger.warning(
                    "Daily runner is already executing or its lock exists"
                )
            else:
                try:
                    succeeded = run_pipeline()

                    if succeeded:
                        last_run_date = now.date()
                    else:
                        logger.error(
                            "Daily pipeline failed; it can be retried "
                            "by restarting the scheduler."
                        )
                finally:
                    release_lock()

        time.sleep(CHECK_INTERVAL)


# ======================================================
# MANUAL RUN SUPPORT
# ======================================================

if __name__ == "__main__":
    import sys

    success = run_pipeline()
    sys.exit(0 if success else 1)