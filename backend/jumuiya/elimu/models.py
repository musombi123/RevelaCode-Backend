# backend/jumuiya/elimu/models.py

from __future__ import annotations

from datetime import datetime, timezone


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# SCHOOL
# =========================================================

def school_document(
    user_id,
    data,
):
    now = now_utc()

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "owner_user_id": str(user_id),

        # -------------------------------------------------
        # SCHOOL IDENTITY
        # -------------------------------------------------

        "name": data["name"],

        "code": data.get(
            "code",
            "",
        ),

        "registration_number": data.get(
            "registration_number",
            "",
        ),

        "description": data.get(
            "description",
            "",
        ),

        "school_type": data.get(
            "school_type",
            "primary",
        ),

        "motto": data.get(
            "motto",
            "",
        ),

        "mission": data.get(
            "mission",
            "",
        ),

        "vision": data.get(
            "vision",
            "",
        ),

        # -------------------------------------------------
        # LEADERSHIP
        # -------------------------------------------------

        "principal_name": data.get(
            "principal_name",
            "",
        ),

        "administrator_name": data.get(
            "administrator_name",
            "",
        ),

        # -------------------------------------------------
        # CONTACT
        # -------------------------------------------------

        "phone": data.get(
            "phone",
            "",
        ),

        "email": data.get(
            "email",
            "",
        ),

        "website": data.get(
            "website",
            "",
        ),

        "postal_address": data.get(
            "postal_address",
            "",
        ),

        # -------------------------------------------------
        # LOCATION
        # -------------------------------------------------

        "location": data.get(
            "location",
            "",
        ),

        "county": data.get(
            "county",
            "",
        ),

        "town": data.get(
            "town",
            "",
        ),

        # -------------------------------------------------
        # BRANDING
        # -------------------------------------------------

        "logo_url": data.get(
            "logo_url",
            "",
        ),

        "report_branding": data.get(
            "report_branding",
            {},
        ),

        # -------------------------------------------------
        # ACADEMIC SETTINGS
        # -------------------------------------------------

        "academic_year": data.get(
            "academic_year",
            "",
        ),

        "current_term": data.get(
            "current_term",
            "",
        ),

        "calendar_year": data.get(
            "calendar_year",
            "",
        ),

        # -------------------------------------------------
        # SETTINGS
        # -------------------------------------------------

        "settings": data.get(
            "settings",
            {},
        ),

        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        "status": "active",

        # -------------------------------------------------
        # AUDIT
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# EDUCATION PROFILE
# =========================================================

def education_profile_document(
    user_id,
    data,
):
    now = now_utc()

    return {
        "user_id": str(user_id),

        "profile_type": data.get(
            "profile_type",
            "school_admin",
        ),

        "full_name": data.get(
            "full_name",
            "",
        ),

        "phone": data.get(
            "phone",
            "",
        ),

        "email": data.get(
            "email",
            "",
        ),

        "school_id": data.get(
            "school_id"
        ),

        "class_name": data.get(
            "class_name",
            "",
        ),

        "admission_number": data.get(
            "admission_number",
            "",
        ),

        "county": data.get(
            "county",
            "",
        ),

        "town": data.get(
            "town",
            "",
        ),

        "status": "active",

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# CLASS
# =========================================================

def class_document(
    school_id,
    data,
):
    now = now_utc()

    return {
        "school_id": str(
            school_id
        ),

        "name": data["name"],

        "level": data.get(
            "level",
            "",
        ),

        "stream": data.get(
            "stream",
            "",
        ),

        "academic_year": data.get(
            "academic_year",
            "",
        ),

        "teacher_id": data.get(
            "teacher_id"
        ),

        "status": "active",

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# STUDENT
# =========================================================

def student_document(
    school_id,
    data,
):
    now = now_utc()

    return {
        "school_id": str(
            school_id
        ),

        "admission_number": data[
            "admission_number"
        ],

        "full_name": data[
            "full_name"
        ],

        "gender": data.get(
            "gender",
            "",
        ),

        "date_of_birth": data.get(
            "date_of_birth",
            "",
        ),

        "class_id": data.get(
            "class_id"
        ),

        "class_name": data.get(
            "class_name",
            "",
        ),

        "guardian_name": data.get(
            "guardian_name",
            "",
        ),

        "guardian_phone": data.get(
            "guardian_phone",
            "",
        ),

        "guardian_email": data.get(
            "guardian_email",
            "",
        ),

        "county": data.get(
            "county",
            "",
        ),

        "town": data.get(
            "town",
            "",
        ),

        "address": data.get(
            "address",
            "",
        ),

        "status": data.get(
            "status",
            "active",
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# LESSON
# =========================================================

def lesson_document(
    user_id,
    school_id,
    data,
):
    now = now_utc()

    return {
        "author_user_id": str(user_id),

        "school_id": str(
            school_id
        ),

        "subject": data["subject"],

        "title": data["title"],

        "description": data.get(
            "description",
            "",
        ),

        "class_name": data.get(
            "class_name",
            "",
        ),

        "content": data.get(
            "content",
            "",
        ),

        "materials": data.get(
            "materials",
            [],
        ),

        "status": "published",

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ASSIGNMENT
# =========================================================

def assignment_document(
    user_id,
    school_id,
    data,
):
    now = now_utc()

    return {
        "teacher_user_id": str(user_id),

        "school_id": str(
            school_id
        ),

        "class_name": data["class_name"],

        "subject": data["subject"],

        "title": data["title"],

        "description": data.get(
            "description",
            "",
        ),

        "due_date": data.get(
            "due_date"
        ),

        "status": "active",

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ATTENDANCE
# =========================================================

def attendance_document(
    user_id,
    school_id,
    student,
    data,
):
    now = now_utc()

    return {
        "school_id": str(
            school_id
        ),

        "student_id": str(
            student["_id"]
        ),

        "student_name": student.get(
            "full_name",
            "",
        ),

        "admission_number": student.get(
            "admission_number",
            "",
        ),

        "class_name": student.get(
            "class_name",
            "",
        ),

        "date": data["date"],

        "status": data.get(
            "status",
            "present",
        ),

        "reason": data.get(
            "reason",
            "",
        ),

        "marked_by": str(
            user_id
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ASSESSMENT
# =========================================================

def assessment_document(
    user_id,
    school_id,
    student,
    data,
):
    now = now_utc()

    score = data.get(
        "score"
    )

    max_score = data.get(
        "max_score",
        100,
    )

    percentage = None

    if (
        score is not None
        and max_score
    ):
        try:
            percentage = round(
                (
                    float(score)
                    / float(max_score)
                )
                * 100,
                2,
            )
        except (
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):
            percentage = None

    return {
        "school_id": str(
            school_id
        ),

        "student_id": str(
            student["_id"]
        ),

        "student_name": student.get(
            "full_name",
            "",
        ),

        "admission_number": student.get(
            "admission_number",
            "",
        ),

        "class_name": student.get(
            "class_name",
            "",
        ),

        "subject": data["subject"],

        "assessment_name": data["assessment_name"],

        "assessment_type": data.get(
            "assessment_type",
            "assessment",
        ),

        "academic_year": data.get(
            "academic_year",
            "",
        ),

        "term": data.get(
            "term",
            "",
        ),

        "score": score,

        "max_score": max_score,

        "percentage": percentage,

        "grade": data.get(
            "grade",
            "",
        ),

        "competency_level": data.get(
            "competency_level",
            "",
        ),

        "remarks": data.get(
            "remarks",
            "",
        ),

        "recorded_by": str(
            user_id
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# FEE
# =========================================================

def fee_document(
    user_id,
    data,
):
    now = now_utc()

    return {
        "student_user_id": str(
            data.get(
                "student_user_id",
                "",
            )
        ),

        "student_id": (
            str(data["student_id"])
            if data.get("student_id")
            else None
        ),

        "school_id": str(
            data["school_id"]
        ),

        "created_by": str(
            user_id
        ),

        "amount": float(
            data["amount"]
        ),

        "currency": data.get(
            "currency",
            "KES",
        ),

        "description": data.get(
            "description",
            "",
        ),

        "term": data.get(
            "term",
            "",
        ),

        "academic_year": data.get(
            "academic_year",
            "",
        ),

        "status": data.get(
            "status",
            "pending",
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# CBC PROJECT
# =========================================================

def cbc_project_document(
    user_id,
    data,
):
    now = now_utc()

    return {
        "student_user_id": str(
            data[
                "student_user_id"
            ]
        ),

        "student_id": (
            str(data["student_id"])
            if data.get("student_id")
            else None
        ),

        "teacher_user_id": str(
            user_id
        ),

        "school_id": data.get(
            "school_id"
        ),

        "title": data["title"],

        "description": data.get(
            "description",
            "",
        ),

        "category": data.get(
            "category",
            "",
        ),

        "skills": data.get(
            "skills",
            [],
        ),

        "materials": data.get(
            "materials",
            [],
        ),

        "status": "active",

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# SCHOOL EVENT
# =========================================================

def event_document(
    user_id,
    school_id,
    data,
):
    now = now_utc()

    return {
        "school_id": str(
            school_id
        ),

        "created_by": str(
            user_id
        ),

        "title": data[
            "title"
        ],

        "event_type": data.get(
            "event_type",
            "school",
        ),

        "description": data.get(
            "description",
            "",
        ),

        "start_date": data[
            "start_date"
        ],

        "end_date": data.get(
            "end_date",
            data["start_date"],
        ),

        "location": data.get(
            "location",
            "",
        ),

        "organizer": data.get(
            "organizer",
            "",
        ),

        "academic_year": data.get(
            "academic_year",
            "",
        ),

        "term": data.get(
            "term",
            "",
        ),

        "is_annual": bool(
            data.get(
                "is_annual",
                False,
            )
        ),

        "status": data.get(
            "status",
            "scheduled",
        ),

        "created_at": now,

        "updated_at": now,
    }
