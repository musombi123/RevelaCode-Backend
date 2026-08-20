from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action

from backend.jumuiya.elimu.models import (
    education_profile_document,
    school_document,
    class_document,
    lesson_document,
    assignment_document,
    fee_document,
    cbc_project_document,
)


def _ser(doc):
    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(out.pop("_id"))

    for key, value in list(out.items()):
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()

    return out


def _many(docs):
    return [_ser(doc) for doc in docs]


# =========================================================
# EDUCATION PROFILE
# =========================================================

def get_profile(user_id):
    doc = collection(
        "jumuiya_education_profiles"
    ).find_one({
        "user_id": str(user_id)
    })

    return _ser(doc)


def save_profile(user_id, data):
    now = datetime.now(timezone.utc)

    update = {
        **data,
        "user_id": str(user_id),
        "updated_at": now,
    }

    doc = collection(
        "jumuiya_education_profiles"
    ).find_one_and_update(
        {"user_id": str(user_id)},
        {
            "$set": update,
            "$setOnInsert": {
                "created_at": now
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "elimu.profile.updated",
        "education_profile",
        doc["_id"],
    )

    return _ser(doc)


# =========================================================
# SCHOOLS
# =========================================================

def create_school(user_id, data):
    doc = school_document(user_id, data)

    result = collection(
        "jumuiya_schools"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "school.created",
        "school",
        result.inserted_id,
    )

    return _ser(doc)


def my_school(user_id):
    doc = collection(
        "jumuiya_schools"
    ).find_one({
        "owner_user_id": str(user_id)
    })

    return _ser(doc)


# =========================================================
# CLASSES
# =========================================================

def create_class(user_id, data):
    school = my_school(user_id)

    if not school:
        raise APIError(
            "Create your school profile first.",
            409,
            "school_required",
        )

    doc = class_document(
        school["id"],
        data,
    )

    result = collection(
        "jumuiya_classes"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "class.created",
        "class",
        result.inserted_id,
    )

    return _ser(doc)


def list_classes(user_id):
    school = my_school(user_id)

    if not school:
        raise APIError(
            "School profile required.",
            409,
            "school_required",
        )

    docs = collection(
        "jumuiya_classes"
    ).find({
        "school_id": school["id"],
        "status": "active",
    }).sort(
        "created_at",
        -1,
    )

    return _many(docs)


# =========================================================
# LESSONS
# =========================================================

def create_lesson(user_id, data):
    doc = lesson_document(
        user_id,
        data,
    )

    result = collection(
        "jumuiya_lessons"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "lesson.created",
        "lesson",
        result.inserted_id,
    )

    return _ser(doc)


def lessons(user_id, subject=None):
    query = {}

    if subject:
        query["subject"] = subject

    docs = collection(
        "jumuiya_lessons"
    ).find(query).sort(
        "created_at",
        -1,
    )

    return _many(docs)


# =========================================================
# ASSIGNMENTS
# =========================================================

def create_assignment(user_id, data):
    doc = assignment_document(
        user_id,
        data,
    )

    result = collection(
        "jumuiya_assignments"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "assignment.created",
        "assignment",
        result.inserted_id,
    )

    return _ser(doc)


def assignments(user_id, class_name=None):
    query = {}

    if class_name:
        query["class_name"] = class_name

    docs = collection(
        "jumuiya_assignments"
    ).find(query).sort(
        "created_at",
        -1,
    )

    return _many(docs)


# =========================================================
# FEES
# =========================================================

def create_fee(user_id, data):
    doc = fee_document(
        user_id,
        data,
    )

    result = collection(
        "jumuiya_fees"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "fee.created",
        "fee",
        result.inserted_id,
    )

    return _ser(doc)


def student_fees(user_id):
    docs = collection(
        "jumuiya_fees"
    ).find({
        "student_user_id": str(user_id)
    }).sort(
        "created_at",
        -1,
    )

    return _many(docs)


# =========================================================
# CBC PROJECTS
# =========================================================

def create_cbc_project(user_id, data):
    doc = cbc_project_document(
        user_id,
        data,
    )

    result = collection(
        "jumuiya_cbc_projects"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "cbc.project.created",
        "cbc_project",
        result.inserted_id,
    )

    return _ser(doc)


def student_projects(user_id):
    docs = collection(
        "jumuiya_cbc_projects"
    ).find({
        "student_user_id": str(user_id)
    }).sort(
        "created_at",
        -1,
    )

    return _many(docs)


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(user_id):

    uid = str(user_id)

    profile = collection(
        "jumuiya_education_profiles"
    ).find_one({
        "user_id": uid
    })

    return {
        "profile": _ser(profile),

        "lessons": collection(
            "jumuiya_lessons"
        ).count_documents({}),

        "assignments": collection(
            "jumuiya_assignments"
        ).count_documents({
            "$or": [
                {"teacher_user_id": uid},
                {
                    "class_name":
                    profile.get("class_name", "")
                    if profile else ""
                },
            ]
        }),

        "projects": collection(
            "jumuiya_cbc_projects"
        ).count_documents({
            "student_user_id": uid
        }),

        "fees": collection(
            "jumuiya_fees"
        ).count_documents({
            "student_user_id": uid
        }),
    }