import json
import os
from datetime import datetime, timedelta, timezone


# ======================================================
# BASE DIRECTORY
# ======================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

CURRENT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SYMBOLS_FILE = os.path.join(
    CURRENT_DIR,
    "symbols_keywords.json"
)

TAGGED_DIR = os.path.join(
    BASE_DIR,
    "events_tagged"
)

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "events_decoded"
)

RETENTION_DAYS = 7

WEEKLY_OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "events_7days.json"
)


# ======================================================
# LOAD SYMBOLS
# ======================================================

def load_symbols():
    with open(
        SYMBOLS_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


# ======================================================
# TIME HELPERS
# ======================================================

def utc_now():
    return datetime.now(
        timezone.utc
    )


def parse_datetime(value):
    """
    Safely parse common ISO timestamps.
    """

    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        try:
            value = str(value).strip()

            if value.endswith("Z"):
                value = value[:-1] + "+00:00"

            dt = datetime.fromisoformat(
                value
            )

        except (
            ValueError,
            TypeError,
        ):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def event_datetime(event):
    """
    Try to determine when the event was published.

    publishedAt is preferred. Falls back to created_at,
    fetched_at or updated_at.
    """

    for field in (
        "publishedAt",
        "published_at",
        "created_at",
        "fetched_at",
        "updated_at",
    ):
        parsed = parse_datetime(
            event.get(field)
        )

        if parsed:
            return parsed

    return None


# ======================================================
# NORMALIZE EVENT
# ======================================================

def normalize_event(event):
    """
    Guarantees every event has a consistent schema.
    """

    if not isinstance(
        event,
        dict,
    ):
        event = {}

    event["headline"] = (
        event.get("headline")
        or ""
    )

    event["description"] = (
        event.get("description")
        or ""
    )

    event["content"] = (
        event.get("content")
        or ""
    )

    event["author"] = (
        event.get("author")
        or ""
    )

    event["url"] = (
        event.get("url")
        or ""
    )

    event["publishedAt"] = (
        event.get("publishedAt")
        or ""
    )

    event["source"] = (
        event.get("source")
        or ""
    )

    event["source_id"] = (
        event.get("source_id")
        or ""
    )

    event["region"] = (
        event.get("region")
        or "global"
    )

    event["location"] = (
        event.get("location")
        or {}
    )

    event["categories"] = (
        event.get("categories")
        or ["general"]
    )

    event["matched_symbols"] = (
        event.get("matched_symbols")
        or []
    )

    event["matched_verses"] = (
        event.get("matched_verses")
        or []
    )

    event["media_type"] = (
        event.get("media_type")
        or "article"
    )

    event["urlToImage"] = (
        event.get("urlToImage")
        or ""
    )

    event["video_url"] = (
        event.get("video_url")
        or ""
    )

    media = (
        event.get("media")
        or {}
    )

    media["images"] = (
        media.get("images")
        or []
    )

    media["videos"] = (
        media.get("videos")
        or []
    )

    event["media"] = media

    if (
        not event["urlToImage"]
        and media["images"]
    ):
        event["urlToImage"] = (
            media["images"][0]
        )

    if (
        not event["video_url"]
        and media["videos"]
    ):
        event["video_url"] = (
            media["videos"][0]
        )

        event["media_type"] = "video"

    return event


# ======================================================
# DECODE EVENT
# ======================================================

def decode_event(
    event,
    symbols,
):

    event = normalize_event(
        event
    )

    matched_symbols = []
    matched_verses = []

    searchable_text = " ".join(
        [
            event["headline"],
            event["description"],
            event["content"],
        ]
    ).lower()

    if not searchable_text.strip():

        event["matched_symbols"] = [
            "general"
        ]

        event["matched_verses"] = []

        return event

    for symbol in symbols.get(
        "symbols",
        [],
    ):

        symbol_name = (
            symbol.get(
                "symbol",
                "",
            )
            .lower()
            .replace(
                " ",
                "_",
            )
            .replace(
                "/",
                "_",
            )
        )

        keywords = symbol.get(
            "keywords",
            []
        )

        verses = symbol.get(
            "verses",
            []
        )

        if any(
            str(keyword).lower()
            in searchable_text
            for keyword in keywords
        ):

            if (
                symbol_name
                and symbol_name
                not in matched_symbols
            ):

                matched_symbols.append(
                    symbol_name
                )

            for verse in verses:

                if (
                    verse
                    not in matched_verses
                ):

                    matched_verses.append(
                        verse
                    )

    if not matched_symbols:
        matched_symbols.append(
            "general"
        )

    event["matched_symbols"] = (
        matched_symbols
    )

    event["matched_verses"] = (
        matched_verses
    )

    print(
        f"[MATCH] "
        f"{event['headline'][:70]} "
        f"-> {matched_symbols}"
    )

    return event


# ======================================================
# EVENT ID / DEDUPLICATION
# ======================================================

def event_key(event):
    """
    Build a stable key so the same story fetched from
    multiple sources/files is not duplicated.
    """

    if event.get("source_id"):
        return (
            "source_id:",
            str(event["source_id"])
        )

    if event.get("url"):
        return (
            "url:",
            str(event["url"])
        )

    return (
        "fallback:",
        str(
            event.get(
                "source",
                ""
            )
        ),
        str(
            event.get(
                "headline",
                ""
            )
        ).strip().lower(),
        str(
            event.get(
                "publishedAt",
                ""
            )
        ),
    )


def deduplicate_events(events):

    seen = set()
    unique = []

    for event in events:

        key = event_key(
            event
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(
            event
        )

    return unique


# ======================================================
# LOAD JSON FILE
# ======================================================

def load_events_file(
    filepath,
):

    try:

        with open(
            filepath,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:

        print(
            f"⚠️ Failed to read "
            f"{filepath}: {exc}"
        )

        return []

    if isinstance(
        data,
        list,
    ):
        return data

    if isinstance(
        data,
        dict,
    ):

        # Support both:
        # {"events": [...]}
        # and a single event object.

        if isinstance(
            data.get("events"),
            list,
        ):
            return data["events"]

        return [data]

    return []


# ======================================================
# WRITE JSON
# ======================================================

def write_json(
    filepath,
    data,
):

    os.makedirs(
        os.path.dirname(filepath),
        exist_ok=True,
    )

    temp_path = (
        filepath
        + ".tmp"
    )

    with open(
        temp_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(
        temp_path,
        filepath,
    )


# ======================================================
# TAGGED FILE DISCOVERY
# ======================================================

def tagged_files():

    if not os.path.exists(
        TAGGED_DIR
    ):
        return []

    files = []

    for filename in os.listdir(
        TAGGED_DIR
    ):

        if not (
            filename.startswith(
                "events_"
            )
            and filename.endswith(
                ".json"
            )
        ):
            continue

        filepath = os.path.join(
            TAGGED_DIR,
            filename,
        )

        if os.path.isfile(
            filepath
        ):
            files.append(
                filepath
            )

    return sorted(
        files,
        key=lambda path: os.path.getmtime(
            path
        ),
        reverse=True,
    )


# ======================================================
# COLLECT LAST 7 DAYS
# ======================================================

def collect_recent_events():
    """
    Read ALL tagged event files and keep only events
    belonging to the last seven days.

    This is the critical retention fix.
    """

    cutoff = (
        utc_now()
        - timedelta(
            days=RETENTION_DAYS
        )
    )

    all_events = []

    files = tagged_files()

    print(
        f"📦 Found {len(files)} tagged event files"
    )

    for filepath in files:

        print(
            f"📖 Reading: "
            f"{os.path.basename(filepath)}"
        )

        events = load_events_file(
            filepath
        )

        for event in events:

            event = normalize_event(
                event
            )

            dt = event_datetime(
                event
            )

            # -------------------------------------------------
            # If event has a valid published date:
            # filter using that date.
            # -------------------------------------------------

            if dt:

                if dt < cutoff:
                    continue

            else:

                # -------------------------------------------------
                # If the event has no published date, use the
                # source file's modification time.
                # -------------------------------------------------

                file_time = datetime.fromtimestamp(
                    os.path.getmtime(filepath),
                    tz=timezone.utc,
                )

                if file_time < cutoff:
                    continue

            all_events.append(
                event
            )

    # ---------------------------------------------------------
    # Remove duplicates
    # ---------------------------------------------------------

    all_events = deduplicate_events(
        all_events
    )

    # ---------------------------------------------------------
    # Newest first
    # ---------------------------------------------------------

    all_events.sort(
        key=lambda event: (
            event_datetime(event)
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    return all_events


# ======================================================
# SAVE DAILY DECODED FILES
# ======================================================

def save_daily_files(
    events,
):
    """
    Also write events into daily decoded files.

    Example:

        events_decoded/
            decoded_2026-08-18.json
            decoded_2026-08-19.json
            decoded_2026-08-20.json
    """

    grouped = {}

    for event in events:

        dt = (
            event_datetime(event)
            or utc_now()
        )

        day = dt.date().isoformat()

        grouped.setdefault(
            day,
            []
        ).append(
            event
        )

    for day, day_events in grouped.items():

        filepath = os.path.join(
            OUTPUT_DIR,
            f"decoded_{day}.json",
        )

        write_json(
            filepath,
            day_events,
        )

        print(
            f"💾 Saved {len(day_events)} events "
            f"to {filepath}"
        )


# ======================================================
# SAVE CONSOLIDATED 7-DAY FILE
# ======================================================

def save_weekly_file(
    events,
):
    """
    This is the file your fetch endpoint can safely read.

        events_decoded/events_7days.json
    """

    payload = {
        "generated_at": utc_now().isoformat(),
        "retention_days": RETENTION_DAYS,
        "count": len(events),
        "events": events,
    }

    write_json(
        WEEKLY_OUTPUT_FILE,
        payload,
    )

    print(
        f"✅ Saved {len(events)} events "
        f"to {WEEKLY_OUTPUT_FILE}"
    )


# ======================================================
# PRUNE OLD DECODED DAILY FILES
# ======================================================

def prune_old_decoded_files():

    if not os.path.exists(
        OUTPUT_DIR
    ):
        return

    cutoff = (
        utc_now()
        - timedelta(
            days=RETENTION_DAYS
        )
    )

    for filename in os.listdir(
        OUTPUT_DIR
    ):

        if not filename.startswith(
            "decoded_"
        ):
            continue

        if not filename.endswith(
            ".json"
        ):
            continue

        filepath = os.path.join(
            OUTPUT_DIR,
            filename,
        )

        try:

            modified = datetime.fromtimestamp(
                os.path.getmtime(filepath),
                tz=timezone.utc,
            )

            if modified < cutoff:

                os.remove(
                    filepath
                )

                print(
                    f"🗑️ Removed old decoded file: "
                    f"{filename}"
                )

        except OSError as exc:

            print(
                f"⚠️ Could not prune "
                f"{filename}: {exc}"
            )


# ======================================================
# MAIN DECODER
# ======================================================

def decode_last_7_days():

    if not os.path.exists(
        TAGGED_DIR
    ):

        print(
            "🚫 events_tagged directory not found"
        )

        return False

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    symbols = load_symbols()

    events = collect_recent_events()

    if not events:

        print(
            "⚠️ No events found in the last "
            f"{RETENTION_DAYS} days."
        )

        # Still create a valid file so the fetch
        # endpoint does not fail or read nothing.
        save_weekly_file([])

        return False

    # -----------------------------------------------------
    # Decode
    # -----------------------------------------------------

    decoded_events = []

    for event in events:

        try:

            decoded_events.append(
                decode_event(
                    event,
                    symbols,
                )
            )

        except Exception as exc:

            print(
                "⚠️ Failed to decode event: "
                f"{event.get('headline', '<unknown>')} "
                f"({exc})"
            )

    # -----------------------------------------------------
    # Final deduplication
    # -----------------------------------------------------

    decoded_events = deduplicate_events(
        decoded_events
    )

    # -----------------------------------------------------
    # Save daily files
    # -----------------------------------------------------

    save_daily_files(
        decoded_events
    )

    # -----------------------------------------------------
    # Save ONE consolidated file
    # -----------------------------------------------------

    save_weekly_file(
        decoded_events
    )

    # -----------------------------------------------------
    # Prune old data
    # -----------------------------------------------------

    prune_old_decoded_files()

    print(
        "======================================"
    )

    print(
        f"✅ Decoded events: "
        f"{len(decoded_events)}"
    )

    print(
        f"📅 Retention: "
        f"{RETENTION_DAYS} days"
    )

    print(
        f"📁 Weekly file: "
        f"{WEEKLY_OUTPUT_FILE}"
    )

    print(
        "======================================"
    )

    return True


# ======================================================
# BACKWARD-COMPATIBLE SINGLE FILE PROCESSING
# ======================================================

def decode_events_file(
    filename,
):

    input_path = os.path.join(
        TAGGED_DIR,
        filename,
    )

    if not os.path.exists(
        input_path
    ):

        print(
            f"❌ Missing file: "
            f"{input_path}"
        )

        return False

    symbols = load_symbols()

    events = load_events_file(
        input_path
    )

    decoded_events = []

    for event in events:

        try:

            decoded_events.append(
                decode_event(
                    event,
                    symbols,
                )
            )

        except Exception as exc:

            print(
                f"⚠️ Failed to decode event: "
                f"{event.get('headline', '<unknown>')} "
                f"({exc})"
            )

    output_path = os.path.join(
        OUTPUT_DIR,
        filename,
    )

    write_json(
        output_path,
        decoded_events,
    )

    print(
        f"✅ Decoded "
        f"{len(decoded_events)} events"
    )

    print(
        f"📁 Saved to "
        f"{output_path}"
    )

    return True


# ======================================================
# CLI
# ======================================================

if __name__ == "__main__":

    if not os.path.exists(
        TAGGED_DIR
    ):

        print(
            "🚫 events_tagged directory not found"
        )

        raise SystemExit(1)

    files = tagged_files()

    if not files:

        print(
            "🚫 No tagged events found. "
            "Run categorize.py first."
        )

        raise SystemExit(0)

    decode_last_7_days()