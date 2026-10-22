"""Scheduled teacher class reminders from published Elimu timetables.

The worker only emits in-app notifications for active school staff and
published timetable entries. A per-teacher/per-entry/per-date key prevents
duplicate reminders when the Render Cron job runs repeatedly.
"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection

logger = logging.getLogger("elimu.teacher_reminders")
NAIROBI = ZoneInfo("Africa/Nairobi")

TIMETABLES = "jumuiya_elimu_timetables"
ENTRIES = "jumuiya_elimu_timetable_entries"
MEMBERS = "jumuiya_elimu_school_members"
CLASSES = "jumuiya_classes"
REMINDERS = "jumuiya_elimu_teacher_reminders"


def _text(value: Any, max_length: int = 180) -> str:
    return str(value or "").strip()[:max_length]


def _minutes(value: Any) -> int | None:
    text = _text(value, 20)
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def _id_candidates(value: Any) -> list[Any]:
    text = _text(value, 100)
    if not text:
        return []
    candidates: list[Any] = [text]
    if ObjectId.is_valid(text):
        candidates.append(ObjectId(text))
    return candidates


def _notification(user_id: str, title: str, message: str, data: dict) -> bool:
    if not user_id:
        return False
    try:
        from backend.jumuiya.notifications.services import notify
        notify(user_id, {
            "title": title,
            "message": message,
            "type": "action_needed",
            "data": data,
        })
        return True
    except Exception:
        logger.exception("Teacher timetable notification failed for %s", user_id)
        return False


def run_teacher_reminders(now: datetime | None = None) -> dict:
    now_local = (now or datetime.now(NAIROBI)).astimezone(NAIROBI)
    day = now_local.strftime("%A").lower()
    schedule_date = now_local.date().isoformat()
    clock = now_local.hour * 60 + now_local.minute

    published = list(collection(TIMETABLES).find({
        "status": "published",
        "school_id": {"$exists": True},
    }).limit(5000))
    published_ids = {
        (_text(item.get("school_id"), 100), str(item.get("_id", "")))
        for item in published
    }
    published_ids |= {
        (_text(item.get("school_id"), 100), _text(item.get("timetable_id"), 100))
        for item in published if item.get("timetable_id")
    }

    checked = 0
    sent = 0
    duplicate_skips = 0
    failures = 0

    entries = collection(ENTRIES).find({
        "day": day,
        "teacher_user_id": {"$exists": True, "$nin": ["", None]},
        "start_time": {"$exists": True},
    }).limit(30000)

    for entry in entries:
        checked += 1
        school_id = _text(entry.get("school_id"), 100)
        teacher_id = _text(entry.get("teacher_user_id"), 160)
        entry_id = str(entry.get("_id", ""))
        timetable_id = _text(entry.get("timetable_id"), 100)
        period_type = _text(entry.get("period_type") or entry.get("type") or "lesson", 30).lower()
        if not school_id or not teacher_id or not entry_id or period_type != "lesson":
            continue
        if (school_id, timetable_id) not in published_ids:
            continue

        start = _minutes(entry.get("start_time"))
        end = _minutes(entry.get("end_time"))
        if start is None or end is None or end <= start:
            continue

        delta = start - clock
        # Notify in the 15 minutes before class and through the first five
        # minutes of class. The persistent key stops repeat notifications.
        if not (-5 <= delta <= 15):
            continue

        member = collection(MEMBERS).find_one({
            "school_id": school_id,
            "user_id": teacher_id,
            "role": "teacher",
            "status": "active",
        })
        if not member:
            continue

        reminder_key = {
            "school_id": school_id,
            "teacher_user_id": teacher_id,
            "entry_id": entry_id,
            "schedule_date": schedule_date,
        }
        reminder_doc = {
            **reminder_key,
            "timetable_id": timetable_id,
            "start_time": entry.get("start_time"),
            "end_time": entry.get("end_time"),
            "created_at": now_local,
            "updated_at": now_local,
        }
        try:
            claim = collection(REMINDERS).update_one(
                reminder_key,
                {"$setOnInsert": reminder_doc},
                upsert=True,
            )
        except DuplicateKeyError:
            duplicate_skips += 1
            continue
        if not claim.upserted_id:
            duplicate_skips += 1
            continue

        class_name = ""
        class_id = _text(entry.get("class_id"), 100)
        if class_id:
            try:
                class_doc = collection(CLASSES).find_one({
                    "school_id": school_id,
                    "_id": {"$in": _id_candidates(class_id)},
                })
                if class_doc:
                    class_name = _text(class_doc.get("class_name") or class_doc.get("name") or class_doc.get("title"), 100)
            except Exception:
                logger.exception("Could not resolve class label for timetable entry %s", entry_id)

        subject = _text(entry.get("subject") or entry.get("subject_name"), 100) or "Scheduled lesson"
        if delta > 0:
            title = "Upcoming class reminder"
            timing = f"Your {subject} lesson starts in {delta} minute{'s' if delta != 1 else ''}."
        else:
            title = "Class attendance reminder"
            timing = f"Your {subject} lesson is scheduled now; open attendance and record the session."

        location = f" for {class_name}" if class_name else ""
        message = f"{timing} Class{location}, {day.title()} {entry.get('start_time')}–{entry.get('end_time')}."
        data = {
            "school_id": school_id,
            "teacher_user_id": teacher_id,
            "entry_id": entry_id,
            "timetable_id": timetable_id,
            "class_id": class_id,
            "class_name": class_name,
            "subject": subject,
            "day": day,
            "start_time": entry.get("start_time"),
            "end_time": entry.get("end_time"),
            "schedule_date": schedule_date,
            "destination": "elimu/attendance",
        }
        if _notification(teacher_id, title, message, data):
            collection(REMINDERS).update_one(
                reminder_key,
                {"$set": {"notification_sent": True, "sent_at": now_local, "updated_at": now_local}},
            )
            sent += 1
        else:
            collection(REMINDERS).delete_one(reminder_key)
            failures += 1

    return {
        "ok": True,
        "timezone": "Africa/Nairobi",
        "schedule_date": schedule_date,
        "day": day,
        "entries_checked": checked,
        "notifications_sent": sent,
        "duplicates_skipped": duplicate_skips,
        "notification_failures": failures,
        "checked_at": now_local.isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_teacher_reminders())
