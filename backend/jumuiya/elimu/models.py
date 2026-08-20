from __future__ import annotations

from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


def education_profile_document(user_id, data):
    now = now_utc()

    return {
        "user_id": str(user_id),
        "profile_type": data.get("profile_type", "student"),
        "full_name": data.get("full_name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "school_id": data.get("school_id"),
        "class_name": data.get("class_name", ""),
        "admission_number": data.get("admission_number", ""),
        "county": data.get("county", ""),
        "town": data.get("town", ""),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def school_document(user_id, data):
    now = now_utc()

    return {
        "owner_user_id": str(user_id),
        "name": data["name"],
        "code": data.get("code", ""),
        "description": data.get("description", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "location": data.get("location", ""),
        "county": data.get("county", ""),
        "school_type": data.get("school_type", "primary"),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def class_document(school_id, data):
    now = now_utc()

    return {
        "school_id": str(school_id),
        "name": data["name"],
        "level": data.get("level", ""),
        "stream": data.get("stream", ""),
        "academic_year": data.get("academic_year", ""),
        "teacher_id": data.get("teacher_id"),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def lesson_document(user_id, data):
    now = now_utc()

    return {
        "author_user_id": str(user_id),
        "school_id": data.get("school_id"),
        "subject": data["subject"],
        "title": data["title"],
        "description": data.get("description", ""),
        "class_name": data.get("class_name", ""),
        "content": data.get("content", ""),
        "materials": data.get("materials", []),
        "status": "published",
        "created_at": now,
        "updated_at": now,
    }


def assignment_document(user_id, data):
    now = now_utc()

    return {
        "teacher_user_id": str(user_id),
        "school_id": data.get("school_id"),
        "class_name": data["class_name"],
        "subject": data["subject"],
        "title": data["title"],
        "description": data.get("description", ""),
        "due_date": data.get("due_date"),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def fee_document(user_id, data):
    now = now_utc()

    return {
        "student_user_id": str(data["student_user_id"]),
        "school_id": str(data["school_id"]),
        "created_by": str(user_id),
        "amount": float(data["amount"]),
        "currency": data.get("currency", "KES"),
        "description": data.get("description", ""),
        "term": data.get("term", ""),
        "academic_year": data.get("academic_year", ""),
        "status": data.get("status", "pending"),
        "created_at": now,
        "updated_at": now,
    }


def cbc_project_document(user_id, data):
    now = now_utc()

    return {
        "student_user_id": str(data["student_user_id"]),
        "teacher_user_id": str(user_id),
        "school_id": data.get("school_id"),
        "title": data["title"],
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "skills": data.get("skills", []),
        "materials": data.get("materials", []),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }