# backend/routes/notifications_routes.py

from __future__ import annotations

from datetime import datetime
import json
import os
from threading import Lock


# =========================================================
# BLUEPRINT
# =========================================================

from flask import Blueprint, jsonify, request


notifications_bp = Blueprint(
    "notifications",
    __name__,
)


# =========================================================
# FILE STORAGE
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

NOTIFICATIONS_FILE = os.path.join(
    BASE_DIR,
    "notifications.json",
)

file_lock = Lock()


# =========================================================
# TIME
# =========================================================

def utc_now():
    return datetime.utcnow().isoformat()


# =========================================================
# NOTIFICATION NORMALIZATION
# =========================================================

def _normalize_notifications(raw_data):
    """
    Convert notification storage into a clean list of
    dictionaries.

    Handles legacy/malformed data such as:

        [
            "some notification",
            {...}
        ]

    and also supports:

        {
            "notifications": [...]
        }

    Every returned item is guaranteed to be a dict with:

        id
        text
        read
        timestamp
    """

    if isinstance(
        raw_data,
        dict,
    ):
        raw_data = raw_data.get(
            "notifications",
            [],
        )

    if not isinstance(
        raw_data,
        list,
    ):
        raw_data = []

    normalized = []

    next_id = 1

    for item in raw_data:

        # -------------------------------------------------
        # Already a dictionary
        # -------------------------------------------------

        if isinstance(
            item,
            dict,
        ):

            notification = dict(
                item
            )

            # ---------------------------------------------
            # ID
            # ---------------------------------------------

            raw_id = notification.get(
                "id"
            )

            try:
                notification_id = int(
                    raw_id
                )
            except (
                TypeError,
                ValueError,
            ):
                notification_id = next_id

            if notification_id <= 0:
                notification_id = next_id

            notification["id"] = (
                notification_id
            )

            # ---------------------------------------------
            # TEXT
            # ---------------------------------------------

            text = (
                notification.get(
                    "text"
                )
                or notification.get(
                    "message"
                )
                or notification.get(
                    "title"
                )
                or ""
            )

            notification["text"] = str(
                text
            )

            # ---------------------------------------------
            # READ
            # ---------------------------------------------

            notification["read"] = bool(
                notification.get(
                    "read",
                    False,
                )
            )

            # ---------------------------------------------
            # TIMESTAMP
            # ---------------------------------------------

            timestamp = (
                notification.get(
                    "timestamp"
                )
                or notification.get(
                    "created_at"
                )
                or notification.get(
                    "createdAt"
                )
                or utc_now()
            )

            notification[
                "timestamp"
            ] = str(timestamp)

            normalized.append(
                notification
            )

            next_id = max(
                next_id,
                notification_id + 1,
            )

            continue

        # -------------------------------------------------
        # Legacy string notification
        # -------------------------------------------------

        if isinstance(
            item,
            str,
        ):

            text = item.strip()

            if not text:
                continue

            normalized.append(
                {
                    "id": next_id,
                    "text": text,
                    "read": False,
                    "timestamp": utc_now(),
                }
            )

            next_id += 1

            continue

        # -------------------------------------------------
        # Ignore unsupported storage values
        # -------------------------------------------------

        continue

    return normalized


# =========================================================
# LOAD NOTIFICATIONS
# =========================================================

def load_notifications():
    """
    Safely load and normalize notification storage.

    This function protects the rest of the application
    from malformed legacy notification entries.
    """

    if not os.path.exists(
        NOTIFICATIONS_FILE
    ):
        return []

    with file_lock:

        try:

            with open(
                NOTIFICATIONS_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                raw_data = json.load(
                    f
                )

        except (
            json.JSONDecodeError,
            OSError,
            TypeError,
        ):

            return []

        return _normalize_notifications(
            raw_data
        )


# =========================================================
# SAVE NOTIFICATIONS
# =========================================================

def save_notifications(
    data,
):
    """
    Save only normalized notification dictionaries.
    """

    normalized = _normalize_notifications(
        data
    )

    with file_lock:

        with open(
            NOTIFICATIONS_FILE,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                normalized,
                f,
                indent=2,
                ensure_ascii=False,
            )

    return normalized


# =========================================================
# NEXT ID
# =========================================================

def _next_id(
    data,
):
    """
    Safely determine the next numeric notification ID.
    """

    highest_id = 0

    for item in data:

        if not isinstance(
            item,
            dict,
        ):
            continue

        try:

            item_id = int(
                item.get(
                    "id",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            item_id = 0

        highest_id = max(
            highest_id,
            item_id,
        )

    return highest_id + 1


# =========================================================
# PUSH NOTIFICATION
# =========================================================

def push_notification(
    text,
    extra=None,
):
    """
    Internal helper for system/user notifications.
    """

    text = str(
        text or ""
    ).strip()

    if not text:
        raise ValueError(
            "Notification text cannot be empty."
        )

    data = load_notifications()

    new_item = {
        "id": _next_id(
            data
        ),
        "text": text,
        "read": False,
        "timestamp": utc_now(),
    }

    if isinstance(
        extra,
        dict,
    ):

        for key, value in extra.items():

            # Never allow extension fields to overwrite
            # core notification identity/state.
            if key in {
                "id",
                "text",
                "read",
                "timestamp",
            }:
                continue

            new_item[key] = value

    data.append(
        new_item
    )

    save_notifications(
        data
    )

    return new_item


# =========================================================
# GET ALL NOTIFICATIONS
# =========================================================

@notifications_bp.route(
    "/api/notifications",
    methods=["GET"],
)
def get_notifications():

    data = load_notifications()

    return jsonify(
        {
            "total": len(
                data
            ),
            "notifications": data,
        }
    ), 200


# =========================================================
# CREATE NOTIFICATION
# =========================================================

@notifications_bp.route(
    "/api/notifications",
    methods=["POST"],
)
def add_notification():

    data = request.get_json(
        silent=True
    )

    if not isinstance(
        data,
        dict,
    ):
        return jsonify(
            {
                "error": "JSON body is required.",
            }
        ), 400

    text = (
        data.get(
            "text"
        )
        or data.get(
            "message"
        )
        or ""
    ).strip()

    if not text:
        return jsonify(
            {
                "error": "Text is required.",
            }
        ), 400

    note = push_notification(
        text,
        extra=data,
    )

    return jsonify(
        note
    ), 201


# =========================================================
# MARK ALL READ
# =========================================================

@notifications_bp.route(
    "/api/notifications/read-all",
    methods=["PUT"],
)
def mark_all_read():

    data = load_notifications()

    for notification in data:

        if isinstance(
            notification,
            dict,
        ):
            notification[
                "read"
            ] = True

    save_notifications(
        data
    )

    return jsonify(
        {
            "message": (
                "All notifications marked as read"
            )
        }
    ), 200


# =========================================================
# MARK SINGLE READ
# =========================================================

@notifications_bp.route(
    "/api/notifications/<int:note_id>",
    methods=["PUT"],
)
def mark_single_read(
    note_id,
):

    data = load_notifications()

    for notification in data:

        if not isinstance(
            notification,
            dict,
        ):
            continue

        try:

            notification_id = int(
                notification.get(
                    "id",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            continue

        if notification_id == note_id:

            notification[
                "read"
            ] = True

            save_notifications(
                data
            )

            return jsonify(
                {
                    "message": (
                        f"Notification {note_id} "
                        "marked as read"
                    )
                }
            ), 200

    return jsonify(
        {
            "error": (
                f"Notification {note_id} not found"
            )
        }
    ), 404


# =========================================================
# DELETE SINGLE NOTIFICATION
# =========================================================

@notifications_bp.route(
    "/api/notifications/<int:note_id>",
    methods=["DELETE"],
)
def delete_notification(
    note_id,
):

    data = load_notifications()

    filtered = []

    found = False

    for notification in data:

        if not isinstance(
            notification,
            dict,
        ):
            continue

        try:

            notification_id = int(
                notification.get(
                    "id",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            notification_id = 0

        if notification_id == note_id:

            found = True
            continue

        filtered.append(
            notification
        )

    if not found:

        return jsonify(
            {
                "error": (
                    f"Notification {note_id} "
                    "not found"
                )
            }
        ), 404

    save_notifications(
        filtered
    )

    return jsonify(
        {
            "message": (
                f"Notification {note_id} deleted"
            )
        }
    ), 200


# =========================================================
# CLEAR ALL
# =========================================================

@notifications_bp.route(
    "/api/notifications",
    methods=["DELETE"],
)
def clear_notifications():

    save_notifications(
        []
    )

    return jsonify(
        {
            "message": (
                "All notifications cleared"
            )
        }
    ), 200
