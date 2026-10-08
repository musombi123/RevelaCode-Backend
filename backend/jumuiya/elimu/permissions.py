# backend/jumuiya/elimu/permissions.py

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Iterable

from bson import ObjectId
from flask import g

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
)


# =========================================================
# COLLECTIONS
# =========================================================

MEMBERS = "jumuiya_elimu_school_members"
SCHOOLS = "jumuiya_schools"
PROFILES = "jumuiya_education_profiles"
STUDENTS = "jumuiya_students"
CLASSES = "jumuiya_classes"


# =========================================================
# ROLES
# =========================================================

ROLE_OWNER = "owner"
ROLE_BURSAR = "bursar"
ROLE_REGISTRAR = "registrar"
ROLE_TEACHER = "teacher"

ROLES = (
    ROLE_OWNER,
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
)


ROLE_LABELS = {
    ROLE_OWNER: "School Owner",
    ROLE_BURSAR: "Bursar",
    ROLE_REGISTRAR: "Registrar",
    ROLE_TEACHER: "Teacher",
}


ROLE_DESCRIPTIONS = {
    ROLE_OWNER: (
        "Full control of the school's Elimu administration, "
        "staff, academics, finance, settings, synchronization "
        "and automation."
    ),
    ROLE_BURSAR: (
        "School finance and fee administration with controlled "
        "access to supporting student and reporting information."
    ),
    ROLE_REGISTRAR: (
        "Student records, classes, academic administration, "
        "teacher assignments and timetable management."
    ),
    ROLE_TEACHER: (
        "Teaching, attendance, lessons, assignments, assessments, "
        "CBC work and assigned-class academic activities."
    ),
}


# =========================================================
# PERMISSIONS
# =========================================================

PERMISSIONS = frozenset(
    {
        # -----------------------------------------------------
        # SCHOOL
        # -----------------------------------------------------
        "school.view",
        "school.update",
        "school.settings",

        # -----------------------------------------------------
        # STAFF
        # -----------------------------------------------------
        "staff.view",
        "staff.invite",
        "staff.update",
        "staff.remove",
        "staff.roles",

        # -----------------------------------------------------
        # STUDENTS
        # -----------------------------------------------------
        "students.view",
        "students.create",
        "students.update",
        "students.delete",

        # -----------------------------------------------------
        # CLASSES
        # -----------------------------------------------------
        "classes.view",
        "classes.create",
        "classes.update",
        "classes.delete",

        # -----------------------------------------------------
        # SUBJECTS / TEACHING ASSIGNMENTS
        # -----------------------------------------------------
        "subjects.view",
        "subjects.manage",
        "teacher_assignments.view",
        "teacher_assignments.manage",

        # -----------------------------------------------------
        # ATTENDANCE
        # -----------------------------------------------------
        "attendance.view",
        "attendance.create",
        "attendance.update",

        # -----------------------------------------------------
        # LESSONS
        # -----------------------------------------------------
        "lessons.view",
        "lessons.create",
        "lessons.update",

        # -----------------------------------------------------
        # ASSIGNMENTS
        # -----------------------------------------------------
        "assignments.view",
        "assignments.create",
        "assignments.update",

        # -----------------------------------------------------
        # ASSESSMENTS
        # -----------------------------------------------------
        "assessments.view",
        "assessments.create",
        "assessments.update",

        # -----------------------------------------------------
        # FEES
        # -----------------------------------------------------
        "fees.view",
        "fees.create",
        "fees.update",
        "fees.reports",

        # -----------------------------------------------------
        # CBC
        # -----------------------------------------------------
        "cbc.view",
        "cbc.create",
        "cbc.update",

        # -----------------------------------------------------
        # CALENDAR
        # -----------------------------------------------------
        "calendar.view",
        "calendar.manage",

        # -----------------------------------------------------
        # TIMETABLE
        # -----------------------------------------------------
        "timetable.view",
        "timetable.generate",
        "timetable.update",
        "timetable.publish",

        # -----------------------------------------------------
        # REPORTS
        # -----------------------------------------------------
        "reports.view",
        "reports.print",
        "reports.export",

        # -----------------------------------------------------
        # CLOUD / DESKTOP SYNCHRONIZATION
        # -----------------------------------------------------
        "sync.view",
        "sync.import",
        "sync.export",
        "sync.resolve",

        # -----------------------------------------------------
        # AUTOMATION
        # -----------------------------------------------------
        "automation.view",
        "automation.manage",
    }
)


# =========================================================
# ROLE PERMISSIONS
# =========================================================

ROLE_PERMISSIONS = {
    # ---------------------------------------------------------
    # OWNER
    # ---------------------------------------------------------

    ROLE_OWNER: set[str](PERMISSIONS),

    # ---------------------------------------------------------
    # BURSAR
    # ---------------------------------------------------------

    ROLE_BURSAR: {
        "school.view",

        "staff.view",

        "students.view",
        "classes.view",

        "fees.view",
        "fees.create",
        "fees.update",
        "fees.reports",

        "reports.view",
        "reports.print",
        "reports.export",

        "calendar.view",

        "sync.view",
        "sync.export",

        "automation.view",
    },

    # ---------------------------------------------------------
    # REGISTRAR
    # ---------------------------------------------------------

    ROLE_REGISTRAR: {
        "school.view",
        "school.update",

        "staff.view",

        "students.view",
        "students.create",
        "students.update",

        "classes.view",
        "classes.create",
        "classes.update",
        "classes.delete",

        "subjects.view",
        "subjects.manage",

        "teacher_assignments.view",
        "teacher_assignments.manage",

        "attendance.view",

        "lessons.view",

        "assignments.view",

        "assessments.view",

        "cbc.view",

        "calendar.view",
        "calendar.manage",

        "timetable.view",
        "timetable.generate",
        "timetable.update",
        "timetable.publish",

        "reports.view",
        "reports.print",
        "reports.export",

        "sync.view",
        "sync.import",
        "sync.export",
        "sync.resolve",

        "automation.view",
    },

    # ---------------------------------------------------------
    # TEACHER
    # ---------------------------------------------------------

    ROLE_TEACHER: {
        "school.view",
        "staff.view",

        "students.view",
        "classes.view",

        "teacher_assignments.view",

        "attendance.view",
        "attendance.create",
        "attendance.update",

        "lessons.view",
        "lessons.create",
        "lessons.update",

        "assignments.view",
        "assignments.create",
        "assignments.update",

        "assessments.view",
        "assessments.create",
        "assessments.update",

        "cbc.view",
        "cbc.create",
        "cbc.update",

        "calendar.view",

        "timetable.view",

        "reports.view",
        "reports.print",
    },
}


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# NORMALIZATION HELPERS
# =========================================================

def _text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _normalize_role(role: Any) -> str:
    value = _text(role).lower()

    if value not in ROLES:
        raise APIError(
            "Unknown Elimu role.",
            422,
            "invalid_elimu_role",
        )

    return value


def _normalize_school_id(value: Any) -> str:
    if isinstance(value, dict):
        value = (
            value.get("school_id")
            or value.get("_id")
        )

    if isinstance(value, ObjectId):
        return str(value)

    return _text(value)


def _normalize_user_id(value: Any) -> str:
    return _text(value)


def _normalize_permission_list(
    permissions: Iterable[str] | None,
) -> set[str]:
    if permissions is None:
        return set()

    output = set()

    for permission in permissions:
        normalized = _text(permission)

        if normalized:
            output.add(normalized)

    return output


# =========================================================
# MONGO ID HELPERS
# =========================================================

def _object_id(value: Any) -> ObjectId | None:
    text_value = _text(value)

    if not text_value:
        return None

    if not ObjectId.is_valid(text_value):
        return None

    return ObjectId(text_value)


def _id_candidates(value: Any) -> list[Any]:
    """
    Support both ObjectId-backed Mongo records and string IDs.

    This is useful while Elimu is evolving and existing records
    may not all use the same identifier representation.
    """

    text_value = _text(value)

    if not text_value:
        return []

    candidates = [text_value]

    object_id = _object_id(text_value)

    if object_id is not None:
        candidates.append(object_id)

    return candidates


# =========================================================
# ROLE / PERMISSION API
# =========================================================

def role_label(role: str) -> str:
    normalized = _normalize_role(role)
    return ROLE_LABELS[normalized]


def role_description(role: str) -> str:
    normalized = _normalize_role(role)
    return ROLE_DESCRIPTIONS[normalized]


def role_permissions(role: str) -> set[str]:
    normalized = _normalize_role(role)

    return set(
        ROLE_PERMISSIONS[normalized]
    )


def effective_permissions(
    role: str,
    custom: Iterable[str] | None = None,
) -> set[str]:
    """
    Calculate the effective permissions for a membership.

    Rules:
      1. A role has a canonical default permission set.
      2. If `permissions` is empty/None, use the role defaults.
      3. If explicit permissions are stored, use only recognized
         permissions from that explicit list.
      4. Unknown permission names are discarded.

    Explicit permission lists must only be writable through
    authorized staff-management operations.
    """

    normalized_role = _normalize_role(role)

    defaults = role_permissions(
        normalized_role
    )

    if custom is None:
        return defaults

    supplied = (
        _normalize_permission_list(custom)
        & set(PERMISSIONS)
    )

    if not supplied:
        return defaults

    return supplied


def has_permission(
    member: dict | None,
    permission: str,
) -> bool:
    if not member:
        return False

    normalized_permission = _text(
        permission
    )

    if normalized_permission not in PERMISSIONS:
        return False

    role = _text(
        member.get("role")
    ).lower()

    if role not in ROLES:
        return False

    permissions = effective_permissions(
        role,
        member.get("permissions"),
    )

    return normalized_permission in permissions


# =========================================================
# SCHOOL LOOKUP
# =========================================================

def _school_matches(
    school: dict,
    school_id: Any,
) -> bool:
    target = _normalize_school_id(
        school_id
    )

    if not target:
        return False

    possible = {
        _normalize_school_id(
            school.get("_id")
        ),
        _normalize_school_id(
            school.get("school_id")
        ),
    }

    return target in {
        value
        for value in possible
        if value
    }


def find_school_for_user(
    user_id: Any,
) -> str | None:
    """
    Resolve the active Elimu school for a user.

    Priority:
      1. Active school membership
      2. School ownership
      3. Active education profile
    """

    uid = _normalize_user_id(
        user_id
    )

    if not uid:
        return None

    member = collection(
        MEMBERS
    ).find_one(
        {
            "user_id": uid,
            "status": "active",
        }
    )

    if member:
        return _normalize_school_id(
            member.get("school_id")
        )

    school = collection(
        SCHOOLS
    ).find_one(
        {
            "owner_user_id": uid,
        }
    )

    if school:
        return _normalize_school_id(
            school
        )

    profile = collection(
        PROFILES
    ).find_one(
        {
            "user_id": uid,
            "status": "active",
        }
    )

    if profile:
        return _normalize_school_id(
            profile.get("school_id")
        )

    return None


# =========================================================
# OWNER MEMBERSHIP
# =========================================================

def ensure_owner_membership(
    user_id: Any,
    school_id: Any,
    invited_by: Any = None,
) -> dict:
    """
    Guarantee that the school's owner has an active owner
    membership record.

    Existing membership is reused.
    """

    uid = _normalize_user_id(
        user_id
    )

    sid = _normalize_school_id(
        school_id
    )

    if not uid or not sid:
        raise APIError(
            "User and school are required.",
            422,
            "invalid_membership",
        )

    existing = collection(
        MEMBERS
    ).find_one(
        {
            "school_id": sid,
            "user_id": uid,
        }
    )

    if existing:
        return existing

    timestamp = now_utc()

    document = {
        "school_id": sid,
        "user_id": uid,
        "role": ROLE_OWNER,
        "status": "active",
        "permissions": sorted(
            PERMISSIONS
        ),
        "assigned_class_ids": [],
        "invited_by": (
            _normalize_user_id(
                invited_by
            )
            or uid
        ),
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    try:
        collection(
            MEMBERS
        ).insert_one(
            document
        )
    except Exception:
        existing = collection(
            MEMBERS
        ).find_one(
            {
                "school_id": sid,
                "user_id": uid,
            }
        )

        if existing:
            return existing

        raise

    return document


# =========================================================
# MEMBERSHIP LOOKUP
# =========================================================

def get_membership(
    user_id: Any,
    school_id: Any = None,
    *,
    allow_owner_fallback: bool = True,
) -> dict | None:
    uid = _normalize_user_id(
        user_id
    )

    if not uid:
        return None

    sid = (
        _normalize_school_id(
            school_id
        )
        if school_id is not None
        else None
    )

    query = {
        "user_id": uid,
        "status": "active",
    }

    if sid:
        query["school_id"] = sid

    member = collection(
        MEMBERS
    ).find_one(
        query
    )

    if member:
        return member

    if not allow_owner_fallback:
        return None

    school_query = {
        "owner_user_id": uid
    }

    schools = collection(
        SCHOOLS
    ).find(
        school_query
    ).limit(20)

    for school in schools:
        resolved_school_id = _normalize_school_id(
            school
        )

        if not resolved_school_id:
            continue

        if sid and resolved_school_id != sid:
            continue

        return ensure_owner_membership(
            uid,
            resolved_school_id,
            uid,
        )

    return None


# =========================================================
# RESOURCE LOOKUP
# =========================================================

def _find_student(
    school_id: str,
    student_id: Any,
) -> dict | None:
    candidates = _id_candidates(
        student_id
    )

    if not candidates:
        return None

    return collection(
        STUDENTS
    ).find_one(
        {
            "school_id": school_id,
            "$or": [
                {
                    "_id": candidate
                }
                for candidate in candidates
            ],
        }
    )


def _student_class_id(
    school_id: str,
    student_id: Any,
) -> str:
    student = _find_student(
        school_id,
        student_id,
    )

    if not student:
        raise APIError(
            "Student not found.",
            404,
            "student_not_found",
        )

    return _text(
        student.get("class_id")
    )


# =========================================================
# CLASS SCOPE
# =========================================================

def teacher_has_class_access(
    member: dict,
    class_id: Any,
) -> bool:
    if (
        _text(
            member.get("role")
        ).lower()
        != ROLE_TEACHER
    ):
        return True

    requested = _text(
        class_id
    )

    if not requested:
        return False

    assigned = {
        _text(value)
        for value in member.get(
            "assigned_class_ids",
            [],
        )
        if _text(value)
    }

    return requested in assigned


def require_class_scope(
    member: dict,
    class_id: Any,
) -> None:
    if (
        _text(
            member.get("role")
        ).lower()
        != ROLE_TEACHER
    ):
        return

    if not teacher_has_class_access(
        member,
        class_id,
    ):
        raise APIError(
            "Teacher access is limited to assigned classes.",
            403,
            "class_scope_denied",
        )


# =========================================================
# STUDENT SCOPE
# =========================================================

def require_student_scope(
    member: dict,
    student_id: Any,
) -> None:
    if (
        _text(
            member.get("role")
        ).lower()
        != ROLE_TEACHER
    ):
        return

    school_id = _normalize_school_id(
        member.get("school_id")
    )

    class_id = _student_class_id(
        school_id,
        student_id,
    )

    require_class_scope(
        member,
        class_id,
    )


# =========================================================
# AUTHORIZATION
# =========================================================

def authorize(
    user_id: Any,
    permission: str,
    school_id: Any = None,
    *,
    class_id: Any = None,
    student_id: Any = None,
) -> dict:
    normalized_permission = _text(
        permission
    )

    if normalized_permission not in PERMISSIONS:
        raise APIError(
            "Unknown Elimu permission.",
            422,
            "invalid_elimu_permission",
        )

    member = get_membership(
        user_id,
        school_id,
    )

    if not member:
        raise APIError(
            "Active Elimu school membership is required.",
            403,
            "elimu_membership_required",
        )

    if _text(
        member.get("status")
    ).lower() != "active":
        raise APIError(
            "Elimu membership is not active.",
            403,
            "elimu_membership_inactive",
        )

    if not has_permission(
        member,
        normalized_permission,
    ):
        raise APIError(
            "You do not have permission to perform this action.",
            403,
            "permission_denied",
        )

    # -----------------------------------------------------
    # TEACHER RESOURCE SCOPING
    # -----------------------------------------------------

    role = _text(
        member.get("role")
    ).lower()

    if role == ROLE_TEACHER:

        # Explicit class scope.
        if class_id is not None:
            require_class_scope(
                member,
                class_id,
            )

        # Student scope is independently checked.
        if student_id is not None:
            require_student_scope(
                member,
                student_id,
            )

    return member


# =========================================================
# FLASK REQUEST MEMBERSHIP
# =========================================================

def set_request_membership(
    member: dict | None,
) -> None:
    g.elimu_membership = member


def request_membership() -> dict | None:
    return getattr(
        g,
        "elimu_membership",
        None,
    )


# =========================================================
# PERMISSION DECORATOR
# =========================================================

def require_permission(
    permission: str,
    *,
    school_id_arg: str | None = None,
    class_id_arg: str | None = None,
    student_id_arg: str | None = None,
):
    """
    Flask authorization decorator.

    The membership is placed in flask.g rather than being injected
    into the endpoint function signature. This keeps existing route
    signatures clean and avoids `_elimu_membership` argument errors.
    """

    def decorator(fn):

        @wraps(fn)
        @require_authenticated
        def wrapped(*args, **kwargs):

            school_id = (
                kwargs.get(
                    school_id_arg
                )
                if school_id_arg
                else None
            )

            class_id = (
                kwargs.get(
                    class_id_arg
                )
                if class_id_arg
                else None
            )

            student_id = (
                kwargs.get(
                    student_id_arg
                )
                if student_id_arg
                else None
            )

            member = authorize(
                current_user_id(),
                permission,
                school_id,
                class_id=class_id,
                student_id=student_id,
            )

            set_request_membership(
                member
            )

            return fn(
                *args,
                **kwargs,
            )

        return wrapped

    return decorator


# =========================================================
# ROLE DECORATOR
# =========================================================

def require_role(
    *roles: str,
):
    allowed_roles = {
        _normalize_role(role)
        for role in roles
    }

    def decorator(fn):

        @wraps(fn)
        @require_authenticated
        def wrapped(*args, **kwargs):

            member = get_membership(
                current_user_id()
            )

            if not member:
                raise APIError(
                    "Active Elimu school membership is required.",
                    403,
                    "elimu_membership_required",
                )

            role = _text(
                member.get("role")
            ).lower()

            if role not in allowed_roles:
                raise APIError(
                    "This Elimu role is not authorized for the action.",
                    403,
                    "role_denied",
                )

            set_request_membership(
                member
            )

            return fn(
                *args,
                **kwargs,
            )

        return wrapped

    return decorator


# =========================================================
# OWNER SHORTCUT
# =========================================================

def require_owner(fn):
    return require_role(
        ROLE_OWNER
    )(fn)


# =========================================================
# MEMBERSHIP VIEW
# =========================================================

def membership_view(
    member: dict | None,
) -> dict:
    if not member:
        return {
            "active": False,
            "school_id": None,
            "user_id": None,
            "role": None,
            "role_label": None,
            "role_description": None,
            "permissions": [],
            "assigned_class_ids": [],
        }

    role = _text(
        member.get("role")
    ).lower()

    permissions = sorted(
        effective_permissions(
            role,
            member.get(
                "permissions"
            ),
        )
    )

    return {
        "active": True,
        "school_id": _normalize_school_id(
            member.get("school_id")
        ),
        "user_id": _normalize_user_id(
            member.get("user_id")
        ),
        "role": role,
        "role_label": role_label(role),
        "role_description": role_description(role),
        "status": _text(
            member.get("status")
        ),
        "permissions": permissions,
        "assigned_class_ids": [
            _text(value)
            for value in member.get(
                "assigned_class_ids",
                [],
            )
            if _text(value)
        ],
    }


# =========================================================
# PERMISSION CATALOG
# =========================================================

def permission_catalog() -> dict:
    """
    Useful for Owner-facing administration screens.

    The frontend can use this to display role/permission
    information without hard-coding the backend's permission
    vocabulary.
    """

    return {
        "roles": [
            {
                "id": role,
                "label": ROLE_LABELS[role],
                "description": ROLE_DESCRIPTIONS[role],
                "permissions": sorted(
                    ROLE_PERMISSIONS[role]
                ),
            }
            for role in ROLES
        ],
        "permissions": sorted(
            PERMISSIONS
        ),
    }


# =========================================================
# SCHOOL ACCESS CONTEXT
# =========================================================

def authorization_context(
    user_id: Any,
) -> dict:
    member = get_membership(
        user_id
    )

    if not member:
        return {
            "allowed": False,
            "membership": membership_view(
                None
            ),
        }

    return {
        "allowed": True,
        "membership": membership_view(
            member
        ),
    }