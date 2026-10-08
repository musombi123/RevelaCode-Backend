# backend/jumuiya/elimu/staff/services.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from bson import ObjectId

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import (
    ROLE_OWNER,
    ROLE_TEACHER,
    authorize,
    effective_permissions,
    get_membership,
)

from .models import (
    COLLECTION,
    INVITATIONS,
    TEACHER_ASSIGNMENTS,
    hash_invitation_token,
    invitation_doc,
    invitation_is_usable,
    membership_doc,
    normalize_class_ids,
    normalize_permissions,
    normalize_text,
    staff_assigned_class_ids,
    staff_learning_area_ids,
    staff_snapshot,
    staff_subjects,
    teacher_reference,
)


# =========================================================
# COLLECTIONS
# =========================================================

STAFF_COLLECTION = COLLECTION

ASSIGNMENTS = TEACHER_ASSIGNMENTS

SCHOOLS = "jumuiya_schools"

CLASSES = "jumuiya_classes"


# =========================================================
# STATUS CATALOG
# =========================================================

STAFF_NON_REMOVED_STATUSES = {
    "active",
    "suspended",
}


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


# =========================================================
# SERIALIZATION
# =========================================================

def _ser(
    document: dict | None,
) -> dict | None:
    if not document:
        return None

    data = dict(
        document
    )

    if isinstance(
        data.get("_id"),
        ObjectId,
    ):
        data["_id"] = str(
            data["_id"]
        )

    for key in (
        "created_at",
        "updated_at",
        "expires_at",
        "accepted_at",
        "activated_at",
        "suspended_at",
        "removed_at",
        "cancelled_at",
    ):
        value = data.get(
            key
        )

        if isinstance(
            value,
            datetime,
        ):
            data[key] = value.isoformat()

    return data


def _many(
    documents,
) -> list[dict]:
    return [
        _ser(document)
        for document in documents
    ]


# =========================================================
# IDENTIFIERS
# =========================================================

def _uid(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _school_id(
    member: Mapping[str, Any],
) -> str:
    school_id = _uid(
        member.get(
            "school_id"
        )
    )

    if not school_id:
        raise APIError(
            "Active Elimu school membership has no school.",
            500,
            "invalid_school_membership",
        )

    return school_id


# =========================================================
# SCHOOL VALIDATION
# =========================================================

def _school_exists(
    school_id: str,
) -> bool:
    query = {
        "$or": [
            {
                "_id": school_id
            },
            {
                "school_id": school_id
            },
        ]
    }

    if ObjectId.is_valid(
        school_id
    ):
        query[
            "$or"
        ].append(
            {
                "_id": ObjectId(
                    school_id
                )
            }
        )

    return (
        collection(
            SCHOOLS
        ).find_one(
            query
        )
        is not None
    )


def _require_school(
    school_id: str,
) -> None:
    if not _school_exists(
        school_id
    ):
        raise APIError(
            "School not found.",
            404,
            "school_not_found",
        )


# =========================================================
# CLASS VALIDATION
# =========================================================

def _class_query(
    school_id: str,
    class_id: str,
) -> dict:
    conditions = [
        {
            "_id": class_id
        },
        {
            "class_id": class_id
        },
    ]

    if ObjectId.is_valid(
        class_id
    ):
        conditions.append(
            {
                "_id": ObjectId(
                    class_id
                )
            }
        )

    return {
        "school_id": school_id,
        "$or": conditions,
    }


def _require_school_class(
    school_id: str,
    class_id: str,
) -> dict:
    normalized = _uid(
        class_id
    )

    if not normalized:
        raise APIError(
            "class_id is required.",
            422,
            "class_required",
        )

    document = (
        collection(
            CLASSES
        ).find_one(
            _class_query(
                school_id,
                normalized,
            )
        )
    )

    if not document:
        raise APIError(
            "Class does not belong to this school.",
            422,
            "class_not_in_school",
        )

    return document


def _class_name(
    class_document: Mapping[str, Any] | None,
) -> str:
    if not isinstance(
        class_document,
        Mapping,
    ):
        return ""

    for key in (
        "name",
        "class_name",
        "title",
    ):
        value = normalize_text(
            class_document.get(key)
        )

        if value:
            return value

    return ""


# =========================================================
# STAFF LOOKUP
# =========================================================

def _find_staff(
    school_id: str,
    staff_user_id: Any,
    *,
    include_removed: bool = False,
) -> dict | None:
    query = {
        "school_id": school_id,
        "user_id": _uid(
            staff_user_id
        ),
    }

    if not include_removed:
        query[
            "status"
        ] = {
            "$ne": "removed"
        }

    return (
        collection(
            STAFF_COLLECTION
        ).find_one(
            query
        )
    )


def _require_staff(
    school_id: str,
    staff_user_id: Any,
    *,
    include_removed: bool = False,
) -> dict:
    document = _find_staff(
        school_id,
        staff_user_id,
        include_removed=include_removed,
    )

    if not document:
        raise APIError(
            "Staff member not found.",
            404,
            "staff_not_found",
        )

    return document


# =========================================================
# OWNER PROTECTION
# =========================================================

def _protect_owner(
    staff_document: Mapping[str, Any],
) -> None:
    target_role = normalize_text(
        staff_document.get(
            "role",
            "",
        )
    ).lower()

    if target_role == ROLE_OWNER:
        raise APIError(
            "The school owner membership is protected.",
            403,
            "owner_role_protected",
        )


# =========================================================
# TEACHER PROFILE HELPERS
# =========================================================

def _teacher_reference(
    staff: Mapping[str, Any],
) -> dict:
    try:
        return teacher_reference(
            staff
        )
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "invalid_teacher_profile",
        )


def _teacher_is_active(
    staff: Mapping[str, Any],
) -> bool:
    return (
        normalize_text(
            staff.get(
                "role"
            )
        ).lower()
        == ROLE_TEACHER
        and normalize_text(
            staff.get(
                "status"
            )
        ).lower()
        == "active"
    )


# =========================================================
# PROFILE MERGING
# =========================================================

def _merge_mapping(
    current: Any,
    incoming: Any,
) -> dict:
    """
    Shallow merge for API profile sections.

    Existing nested fields survive when an update only supplies
    part of a profile section.
    """
    current_dict = (
        dict(current)
        if isinstance(
            current,
            Mapping,
        )
        else {}
    )

    incoming_dict = (
        dict(incoming)
        if isinstance(
            incoming,
            Mapping,
        )
        else {}
    )

    current_dict.update(
        incoming_dict
    )

    return current_dict


def _profile_updates(
    current: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict:
    """
    Convert profile-level API changes into Mongo update fields.

    Top-level aliases are maintained for compatibility with
    existing code and older frontend clients.
    """
    updates: dict = {}

    # -----------------------------------------------------
    # Identity
    # -----------------------------------------------------

    if "identity" in payload:

        identity = _merge_mapping(
            current.get(
                "identity"
            ),
            payload.get(
                "identity"
            ),
        )

        updates[
            "identity"
        ] = identity

        if identity.get(
            "display_name"
        ):
            updates[
                "display_name"
            ] = identity[
                "display_name"
            ]

    # -----------------------------------------------------
    # Employment
    # -----------------------------------------------------

    if "employment" in payload:

        updates[
            "employment"
        ] = _merge_mapping(
            current.get(
                "employment"
            ),
            payload.get(
                "employment"
            ),
        )

    # -----------------------------------------------------
    # Teaching
    # -----------------------------------------------------

    if "teaching" in payload:

        updates[
            "teaching"
        ] = _merge_mapping(
            current.get(
                "teaching"
            ),
            payload.get(
                "teaching"
            ),
        )

    # -----------------------------------------------------
    # Timetable
    # -----------------------------------------------------

    if "timetable" in payload:

        updates[
            "timetable"
        ] = _merge_mapping(
            current.get(
                "timetable"
            ),
            payload.get(
                "timetable"
            ),
        )

    # -----------------------------------------------------
    # Reporting
    # -----------------------------------------------------

    if "reporting" in payload:

        updates[
            "reporting"
        ] = _merge_mapping(
            current.get(
                "reporting"
            ),
            payload.get(
                "reporting"
            ),
        )

    # -----------------------------------------------------
    # Metadata
    # -----------------------------------------------------

    if "metadata" in payload:

        updates[
            "metadata"
        ] = _merge_mapping(
            current.get(
                "metadata"
            ),
            payload.get(
                "metadata"
            ),
        )

    # -----------------------------------------------------
    # Class scope
    # -----------------------------------------------------

    if "assigned_class_ids" in payload:

        class_ids = normalize_class_ids(
            payload.get(
                "assigned_class_ids"
            )
        )

        updates[
            "assigned_class_ids"
        ] = class_ids

        teaching = _merge_mapping(
            updates.get(
                "teaching",
                current.get(
                    "teaching",
                    {},
                ),
            ),
            {},
        )

        teaching[
            "assigned_class_ids"
        ] = class_ids

        updates[
            "teaching"
        ] = teaching

    # -----------------------------------------------------
    # Top-level subjects alias
    # -----------------------------------------------------

    if "subjects" in payload:

        subjects = [
            str(value).strip()
            for value in (
                payload.get(
                    "subjects",
                    [],
                )
                or []
            )
            if str(value).strip()
        ]

        subjects = list(
            dict.fromkeys(
                subjects
            )
        )

        updates[
            "subjects"
        ] = subjects

        teaching = _merge_mapping(
            updates.get(
                "teaching",
                current.get(
                    "teaching",
                    {},
                ),
            ),
            {},
        )

        teaching[
            "subjects"
        ] = subjects

        updates[
            "teaching"
        ] = teaching

    # -----------------------------------------------------
    # Learning areas alias
    # -----------------------------------------------------

    if "learning_area_ids" in payload:

        learning_area_ids = [
            str(value).strip()
            for value in (
                payload.get(
                    "learning_area_ids",
                    [],
                )
                or []
            )
            if str(value).strip()
        ]

        learning_area_ids = list(
            dict.fromkeys(
                learning_area_ids
            )
        )

        updates[
            "learning_area_ids"
        ] = learning_area_ids

        teaching = _merge_mapping(
            updates.get(
                "teaching",
                current.get(
                    "teaching",
                    {},
                ),
            ),
            {},
        )

        teaching[
            "learning_area_ids"
        ] = learning_area_ids

        updates[
            "teaching"
        ] = teaching

    return updates


# =========================================================
# SYNC TEACHER CLASS SCOPE
# =========================================================

def _sync_teacher_scope(
    school_id: str,
    teacher_user_id: str,
    *,
    timestamp: datetime | None = None,
) -> list[str]:
    """
    Rebuild teacher.assigned_class_ids from active assignments.

    This is critical because Timetable authorization relies on
    the membership class scope.
    """
    timestamp = timestamp or now_utc()

    active_assignments = list(
        collection(
            ASSIGNMENTS
        ).find(
            {
                "school_id": school_id,
                "teacher_user_id": teacher_user_id,
                "status": "active",
            },
            {
                "class_id": 1,
            },
        )
    )

    class_ids = sorted(
        {
            _uid(
                item.get(
                    "class_id"
                )
            )
            for item in active_assignments
            if _uid(
                item.get(
                    "class_id"
                )
            )
        }
    )

    teacher = _find_staff(
        school_id,
        teacher_user_id,
        include_removed=True,
    )

    if teacher:

        teaching = _merge_mapping(
            teacher.get(
                "teaching"
            ),
            {},
        )

        teaching[
            "assigned_class_ids"
        ] = class_ids

        collection(
            STAFF_COLLECTION
        ).update_one(
            {
                "_id": teacher[
                    "_id"
                ]
            },
            {
                "$set": {
                    "assigned_class_ids": class_ids,
                    "teaching": teaching,
                    "updated_at": timestamp,
                }
            },
        )

    return class_ids


# =========================================================
# LIST STAFF
# =========================================================

def list_staff(
    user_id: Any,
) -> dict:
    member = authorize(
        user_id,
        "staff.view",
    )

    school_id = _school_id(
        member
    )

    documents = (
        collection(
            STAFF_COLLECTION
        )
        .find(
            {
                "school_id": school_id,
                "status": {
                    "$nin": [
                        "removed",
                    ]
                },
            }
        )
        .sort(
            "created_at",
            1,
        )
    )

    staff = _many(
        documents
    )

    return {
        "school_id": school_id,
        "count": len(
            staff
        ),
        "staff": staff,
    }


# =========================================================
# GET STAFF
# =========================================================

def get_staff(
    user_id: Any,
    staff_user_id: Any,
) -> dict:
    member = authorize(
        user_id,
        "staff.view",
    )

    school_id = _school_id(
        member
    )

    document = _require_staff(
        school_id,
        staff_user_id,
    )

    result = _ser(
        document
    )

    # -----------------------------------------------------
    # Attach live assignment summary for teachers.
    # -----------------------------------------------------

    if (
        normalize_text(
            document.get(
                "role"
            )
        ).lower()
        == ROLE_TEACHER
    ):
        assignments = list(
            collection(
                ASSIGNMENTS
            ).find(
                {
                    "school_id": school_id,
                    "teacher_user_id": _uid(
                        staff_user_id
                    ),
                }
            ).sort(
                "created_at",
                1,
            )
        )

        result[
            "teacher_assignments"
        ] = _many(
            assignments
        )

    return result


# =========================================================
# INVITE STAFF
# =========================================================

def invite_staff(
    user_id: Any,
    payload: dict,
) -> dict:
    member = authorize(
        user_id,
        "staff.invite",
    )

    school_id = _school_id(
        member
    )

    _require_school(
        school_id
    )

    role = normalize_text(
        payload.get(
            "role",
            "",
        )
    ).lower()

    if role == ROLE_OWNER:
        raise APIError(
            "Owner cannot be invited through staff management.",
            403,
            "owner_role_protected",
        )

    if not role:
        raise APIError(
            "Staff role is required.",
            422,
            "staff_role_required",
        )

    timestamp = now_utc()

    # -----------------------------------------------------
    # Direct existing-user link
    # -----------------------------------------------------

    target_user_id = _uid(
        payload.get(
            "user_id"
        )
    )

    if target_user_id:

        existing = _find_staff(
            school_id,
            target_user_id,
        )

        if existing:
            raise APIError(
                "User is already linked to this school.",
                409,
                "staff_exists",
            )

        document = membership_doc(
            school_id=school_id,
            user_id=target_user_id,
            role=role,
            invited_by=user_id,
            status="active",
            permissions=payload.get(
                "permissions"
            ),
            assigned_class_ids=payload.get(
                "assigned_class_ids"
            ),
            identity=payload.get(
                "identity"
            ),
            employment=payload.get(
                "employment"
            ),
            teaching=payload.get(
                "teaching"
            ),
            timetable=payload.get(
                "timetable"
            ),
            reporting=payload.get(
                "reporting"
            ),
            metadata=payload.get(
                "metadata"
            ) or {},
            activated_at=timestamp,
        )

        try:
            result = collection(
                STAFF_COLLECTION
            ).insert_one(
                document
            )
        except Exception as exc:
            existing = _find_staff(
                school_id,
                target_user_id,
            )

            if existing:
                raise APIError(
                    "User is already linked to this school.",
                    409,
                    "staff_exists",
                )

            raise exc

        document[
            "_id"
        ] = result.inserted_id

        return {
            "mode": "user_link",
            "staff": _ser(
                document
            ),
        }

    # -----------------------------------------------------
    # Email invitation
    # -----------------------------------------------------

    email = normalize_text(
        payload.get(
            "email",
            "",
        )
    ).lower()

    if not email:
        raise APIError(
            "user_id or email is required.",
            422,
            "invitation_recipient_required",
        )

    existing_invitation = (
        collection(
            INVITATIONS
        ).find_one(
            {
                "school_id": school_id,
                "email": email,
                "status": "invited",
            }
        )
    )

    if (
        existing_invitation
        and invitation_is_usable(
            existing_invitation
        )
    ):
        raise APIError(
            "An active invitation already exists for this email.",
            409,
            "invitation_exists",
        )

    document, raw_token = invitation_doc(
        school_id=school_id,
        email=email,
        role=role,
        invited_by=user_id,
        permissions=payload.get(
            "permissions"
        ),
        assigned_class_ids=payload.get(
            "assigned_class_ids"
        ),
        identity=payload.get(
            "identity"
        ),
        employment=payload.get(
            "employment"
        ),
        teaching=payload.get(
            "teaching"
        ),
        timetable=payload.get(
            "timetable"
        ),
        reporting=payload.get(
            "reporting"
        ),
        metadata=payload.get(
            "metadata"
        ) or {},
        expires_in_days=payload.get(
            "expires_in_days",
            7,
        ),
    )

    result = collection(
        INVITATIONS
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    return {
        "mode": "email_invitation",
        "invitation": _ser(
            document
        ),
        "invitation_token": raw_token,
    }


# =========================================================
# UPDATE STAFF
# =========================================================

def update_staff(
    user_id: Any,
    staff_user_id: Any,
    payload: dict,
) -> dict:
    member = authorize(
        user_id,
        "staff.update",
    )

    school_id = _school_id(
        member
    )

    target_user_id = _uid(
        staff_user_id
    )

    requester_user_id = _uid(
        user_id
    )

    if (
        target_user_id
        == requester_user_id
    ):
        raise APIError(
            "Use account settings for your own identity.",
            400,
            "self_staff_update_blocked",
        )

    document = _require_staff(
        school_id,
        target_user_id,
    )

    _protect_owner(
        document
    )

    updates = dict(
        payload
    )

    current_role = normalize_text(
        document.get(
            "role",
            "",
        )
    ).lower()

    new_role = normalize_text(
        updates.get(
            "role",
            current_role,
        )
    ).lower()

    if new_role == ROLE_OWNER:
        raise APIError(
            "Owner role cannot be assigned here.",
            403,
            "owner_role_protected",
        )

    # -----------------------------------------------------
    # Permissions
    # -----------------------------------------------------

    if "permissions" in updates:

        requested_permissions = updates.get(
            "permissions"
        )

        updates[
            "permissions"
        ] = sorted(
            effective_permissions(
                new_role,
                requested_permissions,
            )
        )

    # -----------------------------------------------------
    # Profile updates
    # -----------------------------------------------------

    profile_updates = _profile_updates(
        document,
        payload,
    )

    updates.update(
        profile_updates
    )

    # -----------------------------------------------------
    # Assigned classes
    # -----------------------------------------------------

    if "assigned_class_ids" in updates:

        class_ids = normalize_class_ids(
            updates.get(
                "assigned_class_ids"
            )
        )

        if (
            class_ids
            and new_role
            != ROLE_TEACHER
        ):
            raise APIError(
                "Only teachers may have assigned classes.",
                422,
                "teacher_class_scope_invalid",
            )

        for class_id in class_ids:
            _require_school_class(
                school_id,
                class_id,
            )

        updates[
            "assigned_class_ids"
        ] = class_ids

        teaching = _merge_mapping(
            updates.get(
                "teaching",
                document.get(
                    "teaching",
                    {},
                ),
            ),
            {},
        )

        teaching[
            "assigned_class_ids"
        ] = class_ids

        updates[
            "teaching"
        ] = teaching

    # -----------------------------------------------------
    # Role transition away from Teacher
    # -----------------------------------------------------

    role_changed = (
        new_role
        != current_role
    )

    if (
        role_changed
        and current_role
        == ROLE_TEACHER
        and new_role
        != ROLE_TEACHER
    ):

        updates[
            "assigned_class_ids"
        ] = []

        teaching = _merge_mapping(
            updates.get(
                "teaching",
                document.get(
                    "teaching",
                    {},
                ),
            ),
            {},
        )

        teaching[
            "assigned_class_ids"
        ] = []

        updates[
            "teaching"
        ] = teaching

        collection(
            ASSIGNMENTS
        ).update_many(
            {
                "school_id": school_id,
                "teacher_user_id": target_user_id,
                "status": "active",
            },
            {
                "$set": {
                    "status": "inactive",
                    "updated_at": now_utc(),
                }
            },
        )

    # -----------------------------------------------------
    # Status transition
    # -----------------------------------------------------

    new_status = normalize_text(
        updates.get(
            "status",
            document.get(
                "status",
                "active",
            ),
        )
    ).lower()

    if new_status in {
        "suspended",
        "removed",
    }:

        updates[
            "assigned_class_ids"
        ] = []

        teaching = _merge_mapping(
            updates.get(
                "teaching",
                document.get(
                    "teaching",
                    {},
                ),
            ),
            {},
        )

        teaching[
            "assigned_class_ids"
        ] = []

        updates[
            "teaching"
        ] = teaching

        collection(
            ASSIGNMENTS
        ).update_many(
            {
                "school_id": school_id,
                "teacher_user_id": target_user_id,
                "status": "active",
            },
            {
                "$set": {
                    "status": "inactive",
                    "updated_at": now_utc(),
                }
            },
        )

    # -----------------------------------------------------
    # Lifecycle timestamps
    # -----------------------------------------------------

    timestamp = now_utc()

    updates[
        "updated_at"
    ] = timestamp

    if new_status == "suspended":
        updates[
            "suspended_at"
        ] = timestamp

    elif new_status == "removed":
        updates[
            "removed_at"
        ] = timestamp

    elif (
        new_status == "active"
        and document.get(
            "status"
        ) == "suspended"
    ):
        updates[
            "suspended_at"
        ] = None

    # -----------------------------------------------------
    # Protect immutable identity fields.
    # -----------------------------------------------------

    updates.pop(
        "school_id",
        None,
    )

    updates.pop(
        "user_id",
        None,
    )

    updates.pop(
        "staff_id",
        None,
    )

    updates.pop(
        "invited_by",
        None,
    )

    updates.pop(
        "created_at",
        None,
    )

    # -----------------------------------------------------
    # Save
    # -----------------------------------------------------

    result = collection(
        STAFF_COLLECTION
    ).update_one(
        {
            "_id": document[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": updates
        },
    )

    if not result.matched_count:
        raise APIError(
            "Staff member could not be updated.",
            409,
            "staff_update_failed",
        )

    # Rebuild teacher scope from assignments after any
    # teacher membership mutation.
    if (
        new_role
        == ROLE_TEACHER
        and new_status
        == "active"
    ):
        _sync_teacher_scope(
            school_id,
            target_user_id,
            timestamp=timestamp,
        )

    updated = (
        collection(
            STAFF_COLLECTION
        ).find_one(
            {
                "_id": document[
                    "_id"
                ],
                "school_id": school_id,
            }
        )
    )

    return _ser(
        updated
    )


# =========================================================
# REMOVE STAFF
# =========================================================

def remove_staff(
    user_id: Any,
    staff_user_id: Any,
) -> dict:
    member = authorize(
        user_id,
        "staff.remove",
    )

    school_id = _school_id(
        member
    )

    target_user_id = _uid(
        staff_user_id
    )

    requester_user_id = _uid(
        user_id
    )

    if (
        target_user_id
        == requester_user_id
    ):
        raise APIError(
            "You cannot remove your own school membership.",
            400,
            "self_remove_blocked",
        )

    document = _require_staff(
        school_id,
        target_user_id,
    )

    _protect_owner(
        document
    )

    timestamp = now_utc()

    teaching = _merge_mapping(
        document.get(
            "teaching"
        ),
        {},
    )

    teaching[
        "assigned_class_ids"
    ] = []

    result = collection(
        STAFF_COLLECTION
    ).update_one(
        {
            "_id": document[
                "_id"
            ],
            "school_id": school_id,
            "status": {
                "$ne": "removed"
            },
        },
        {
            "$set": {
                "status": "removed",
                "assigned_class_ids": [],
                "teaching": teaching,
                "removed_at": timestamp,
                "updated_at": timestamp,
            }
        },
    )

    if not result.matched_count:
        raise APIError(
            "Staff member not found.",
            404,
            "staff_not_found",
        )

    collection(
        ASSIGNMENTS
    ).update_many(
        {
            "school_id": school_id,
            "teacher_user_id": target_user_id,
            "status": "active",
        },
        {
            "$set": {
                "status": "inactive",
                "updated_at": timestamp,
            }
        },
    )

    return {
        "removed": True,
        "user_id": target_user_id,
        "school_id": school_id,
    }


# =========================================================
# ACCEPT INVITATION
# =========================================================

def accept_invitation(
    user_id: Any,
    token: str,
) -> dict:
    raw_token = str(
        token or ""
    ).strip()

    if not raw_token:
        raise APIError(
            "Invitation token is required.",
            422,
            "invitation_token_required",
        )

    try:
        token_hash = hash_invitation_token(
            raw_token
        )
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "invalid_invitation_token",
        )

    invitation = (
        collection(
            INVITATIONS
        ).find_one(
            {
                "token_hash": token_hash,
                "status": "invited",
            }
        )
    )

    if not invitation:
        raise APIError(
            "Invitation is invalid or already used.",
            404,
            "invitation_not_found",
        )

    if not invitation_is_usable(
        invitation
    ):
        raise APIError(
            "This invitation has expired or is no longer usable.",
            410,
            "invitation_expired",
        )

    school_id = _uid(
        invitation.get(
            "school_id"
        )
    )

    current_user = _uid(
        user_id
    )

    if (
        not school_id
        or not current_user
    ):
        raise APIError(
            "Invalid invitation.",
            422,
            "invalid_invitation",
        )

    existing = _find_staff(
        school_id,
        current_user,
    )

    if existing:
        raise APIError(
            "You are already linked to this school.",
            409,
            "staff_exists",
        )

    timestamp = now_utc()

    profile = (
        invitation.get(
            "profile",
            {}
        )
        if isinstance(
            invitation.get(
                "profile",
                {},
            ),
            Mapping,
        )
        else {}
    )

    teaching = (
        profile.get(
            "teaching",
            {},
        )
        if isinstance(
            profile.get(
                "teaching",
                {},
            ),
            Mapping,
        )
        else {}
    )

    # Top-level invitation class scope remains canonical.
    assigned_class_ids = normalize_class_ids(
        invitation.get(
            "assigned_class_ids",
            teaching.get(
                "assigned_class_ids",
                [],
            ),
        )
    )

    document = membership_doc(
        school_id=school_id,
        user_id=current_user,
        role=invitation.get(
            "role"
        ),
        invited_by=invitation.get(
            "invited_by"
        ),
        status="active",
        permissions=invitation.get(
            "permissions"
        ),
        assigned_class_ids=assigned_class_ids,
        identity=profile.get(
            "identity"
        ),
        employment=profile.get(
            "employment"
        ),
        teaching=profile.get(
            "teaching"
        ),
        timetable=profile.get(
            "timetable"
        ),
        reporting=profile.get(
            "reporting"
        ),
        metadata=profile.get(
            "metadata"
        )
        or invitation.get(
            "metadata"
        )
        or {},
        accepted_at=timestamp,
        activated_at=timestamp,
    )

    try:
        result = collection(
            STAFF_COLLECTION
        ).insert_one(
            document
        )

    except Exception:

        existing = _find_staff(
            school_id,
            current_user,
        )

        if existing:
            raise APIError(
                "You are already linked to this school.",
                409,
                "staff_exists",
            )

        raise

    document[
        "_id"
    ] = result.inserted_id

    # -----------------------------------------------------
    # Consume invitation atomically enough for the current
    # Mongo implementation: token + status must still match.
    # -----------------------------------------------------

    invitation_update = (
        collection(
            INVITATIONS
        ).update_one(
            {
                "_id": invitation[
                    "_id"
                ],
                "status": "invited",
                "token_hash": token_hash,
            },
            {
                "$set": {
                    "status": "accepted",
                    "accepted_at": timestamp,
                    "accepted_by": current_user,
                    "updated_at": timestamp,
                }
            },
        )
    )

    if not invitation_update.matched_count:
        # Roll back the newly-created membership if this request
        # lost the final invitation-consumption race.
        collection(
            STAFF_COLLECTION
        ).delete_one(
            {
                "_id": result.inserted_id,
                "school_id": school_id,
                "user_id": current_user,
            }
        )

        raise APIError(
            "Invitation could not be finalized safely.",
            409,
            "invitation_finalize_conflict",
        )

    return _ser(
        document
    )


# =========================================================
# ASSIGN TEACHER
# =========================================================

def assign_teacher(
    user_id: Any,
    payload: dict,
) -> dict:
    member = authorize(
        user_id,
        "teacher_assignments.manage",
    )

    school_id = _school_id(
        member
    )

    teacher_user_id = _uid(
        payload.get(
            "teacher_user_id"
        )
    )

    class_id = _uid(
        payload.get(
            "class_id"
        )
    )

    if not teacher_user_id:
        raise APIError(
            "teacher_user_id is required.",
            422,
            "teacher_required",
        )

    if not class_id:
        raise APIError(
            "class_id is required.",
            422,
            "class_required",
        )

    class_document = _require_school_class(
        school_id,
        class_id,
    )

    # -----------------------------------------------------
    # Validate teacher
    # -----------------------------------------------------

    teacher_membership = get_membership(
        teacher_user_id,
        school_id,
        allow_owner_fallback=False,
    )

    if not teacher_membership:
        raise APIError(
            "Teacher is not a member of this school.",
            422,
            "teacher_not_member",
        )

    teacher = (
        collection(
            STAFF_COLLECTION
        ).find_one(
            {
                "school_id": school_id,
                "user_id": teacher_user_id,
                "role": ROLE_TEACHER,
                "status": "active",
            }
        )
    )

    if not teacher:
        raise APIError(
            "Active teacher membership not found.",
            422,
            "teacher_required",
        )

    # -----------------------------------------------------
    # Subjects / learning areas
    # -----------------------------------------------------

    subjects = [
        str(value).strip()
        for value in (
            payload.get(
                "subjects",
                [],
            )
            or []
        )
        if str(value).strip()
    ]

    subjects = list(
        dict.fromkeys(
            subjects
        )
    )

    learning_area_ids = [
        str(value).strip()
        for value in (
            payload.get(
                "learning_area_ids",
                [],
            )
            or []
        )
        if str(value).strip()
    ]

    learning_area_ids = list(
        dict.fromkeys(
            learning_area_ids
        )
    )

    status = normalize_text(
        payload.get(
            "status",
            "active",
        )
    ).lower()

    if status not in {
        "active",
        "inactive",
    }:
        raise APIError(
            "Invalid teacher assignment status.",
            422,
            "invalid_assignment_status",
        )

    timestamp = now_utc()

    reference = _teacher_reference(
        teacher
    )

    # -----------------------------------------------------
    # Assignment document
    # -----------------------------------------------------

    assignment_update = {
        "school_id": school_id,
        "teacher_user_id": teacher_user_id,
        "class_id": class_id,

        "class_name": _class_name(
            class_document
        ),

        "teacher_name": reference.get(
            "teacher_name",
            "",
        ),

        "employee_number": reference.get(
            "employee_number"
        ),

        "subjects": subjects,

        "learning_area_ids": learning_area_ids,

        "status": status,

        "updated_at": timestamp,
    }

    collection(
        ASSIGNMENTS
    ).update_one(
        {
            "school_id": school_id,
            "teacher_user_id": teacher_user_id,
            "class_id": class_id,
        },
        {
            "$set": assignment_update,
            "$setOnInsert": {
                "created_at": timestamp,
            },
        },
        upsert=True,
    )

    # -----------------------------------------------------
    # Sync staff teaching profile
    # -----------------------------------------------------

    current_subjects = set(
        staff_subjects(
            teacher
        )
    )

    current_subjects.update(
        subjects
    )

    current_learning_area_ids = set(
        staff_learning_area_ids(
            teacher
        )
    )

    current_learning_area_ids.update(
        learning_area_ids
    )

    teaching = dict(
        teacher.get(
            "teaching",
            {},
        )
        or {}
    )

    teaching[
        "subjects"
    ] = sorted(
        current_subjects
    )

    teaching[
        "learning_area_ids"
    ] = sorted(
        current_learning_area_ids
    )

    # -----------------------------------------------------
    # Rebuild class scope from assignments instead of trusting
    # the incoming class list.
    # -----------------------------------------------------

    assigned_class_ids = _sync_teacher_scope(
        school_id,
        teacher_user_id,
        timestamp=timestamp,
    )

    teaching[
        "assigned_class_ids"
    ] = assigned_class_ids

    collection(
        STAFF_COLLECTION
    ).update_one(
        {
            "_id": teacher[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": {
                "teaching": teaching,
                "assigned_class_ids": assigned_class_ids,
                "subjects": sorted(
                    current_subjects
                ),
                "learning_area_ids": sorted(
                    current_learning_area_ids
                ),
                "updated_at": timestamp,
            }
        },
    )

    result = (
        collection(
            ASSIGNMENTS
        ).find_one(
            {
                "school_id": school_id,
                "teacher_user_id": teacher_user_id,
                "class_id": class_id,
            }
        )
    )

    return _ser(
        result
    )


# =========================================================
# REMOVE / DEACTIVATE TEACHER ASSIGNMENT
# =========================================================

def deactivate_teacher_assignment(
    user_id: Any,
    teacher_user_id: Any,
    class_id: Any,
) -> dict:
    """
    Explicitly deactivate one teacher/class relationship.

    Existing route files do not currently expose this operation,
    but the service is ready for the later timetable/frontend layer.
    """

    member = authorize(
        user_id,
        "teacher_assignments.manage",
    )

    school_id = _school_id(
        member
    )

    teacher_id = _uid(
        teacher_user_id
    )

    target_class_id = _uid(
        class_id
    )

    if not teacher_id:
        raise APIError(
            "teacher_user_id is required.",
            422,
            "teacher_required",
        )

    if not target_class_id:
        raise APIError(
            "class_id is required.",
            422,
            "class_required",
        )

    timestamp = now_utc()

    result = collection(
        ASSIGNMENTS
    ).update_one(
        {
            "school_id": school_id,
            "teacher_user_id": teacher_id,
            "class_id": target_class_id,
            "status": "active",
        },
        {
            "$set": {
                "status": "inactive",
                "updated_at": timestamp,
            }
        },
    )

    if not result.matched_count:
        raise APIError(
            "Active teacher assignment not found.",
            404,
            "teacher_assignment_not_found",
        )

    assigned_class_ids = _sync_teacher_scope(
        school_id,
        teacher_id,
        timestamp=timestamp,
    )

    return {
        "updated": True,
        "school_id": school_id,
        "teacher_user_id": teacher_id,
        "class_id": target_class_id,
        "assigned_class_ids": assigned_class_ids,
    }


# =========================================================
# LIST TEACHER ASSIGNMENTS
# =========================================================

def list_assignments(
    user_id: Any,
    teacher_user_id: Any = None,
) -> dict:
    member = authorize(
        user_id,
        "teacher_assignments.view",
    )

    school_id = _school_id(
        member
    )

    requester_id = _uid(
        user_id
    )

    requester_role = normalize_text(
        member.get(
            "role",
            "",
        )
    ).lower()

    target_teacher_id = (
        _uid(
            teacher_user_id
        )
        if teacher_user_id
        else None
    )

    # -----------------------------------------------------
    # Teacher scope
    # -----------------------------------------------------

    if requester_role == ROLE_TEACHER:

        if (
            target_teacher_id
            and target_teacher_id
            != requester_id
        ):
            raise APIError(
                "Teachers may only view their own teaching assignments.",
                403,
                "teacher_assignment_scope_denied",
            )

        target_teacher_id = requester_id

    # -----------------------------------------------------
    # Query
    # -----------------------------------------------------

    query = {
        "school_id": school_id
    }

    if target_teacher_id:
        query[
            "teacher_user_id"
        ] = target_teacher_id

    documents = list(
        collection(
            ASSIGNMENTS
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "created_at",
                    1,
                ),
                (
                    "teacher_user_id",
                    1,
                ),
                (
                    "class_id",
                    1,
                ),
            ]
        )
    )

    # -----------------------------------------------------
    # Return a useful teacher summary.
    # -----------------------------------------------------

    result = {
        "school_id": school_id,
        "teacher_user_id": target_teacher_id,
        "assignments": _many(
            documents
        ),
    }

    if target_teacher_id:

        teacher = _find_staff(
            school_id,
            target_teacher_id,
        )

        if teacher:
            result[
                "teacher"
            ] = staff_snapshot(
                teacher,
                include_contact=False,
            )

    return result


# =========================================================
# TEACHER DIRECTORY
# =========================================================

def list_teachers(
    user_id: Any,
) -> dict:
    """
    Teacher-focused directory for Timetable and assignment UIs.
    """

    member = authorize(
        user_id,
        "staff.view",
    )

    school_id = _school_id(
        member
    )

    documents = list(
        collection(
            STAFF_COLLECTION
        )
        .find(
            {
                "school_id": school_id,
                "role": ROLE_TEACHER,
                "status": "active",
            }
        )
        .sort(
            [
                (
                    "display_name",
                    1,
                ),
                (
                    "created_at",
                    1,
                ),
            ]
        )
    )

    teachers = []

    for document in documents:

        item = staff_snapshot(
            document,
            include_contact=False,
        )

        reference = _teacher_reference(
            document
        )

        item.update(
            {
                "teacher_user_id": (
                    reference[
                        "teacher_user_id"
                    ]
                ),
                "teacher_name": (
                    reference[
                        "teacher_name"
                    ]
                ),
                "employee_number": (
                    reference[
                        "employee_number"
                    ]
                ),
                "subjects": (
                    reference[
                        "subjects"
                    ]
                ),
                "learning_area_ids": (
                    reference[
                        "learning_area_ids"
                    ]
                ),
                "assigned_class_ids": (
                    reference[
                        "assigned_class_ids"
                    ]
                ),
            }
        )

        teachers.append(
            item
        )

    return {
        "school_id": school_id,
        "count": len(
            teachers
        ),
        "teachers": teachers,
    }


# =========================================================
# REBUILD ALL TEACHER SCOPES
# =========================================================

def rebuild_teacher_scopes(
    user_id: Any,
) -> dict:
    """
    Repair/synchronize all teacher membership class scopes
    from the authoritative assignment collection.

    This will also be useful for data migration and Sync.
    """

    member = authorize(
        user_id,
        "teacher_assignments.manage",
    )

    school_id = _school_id(
        member
    )

    teachers = list(
        collection(
            STAFF_COLLECTION
        ).find(
            {
                "school_id": school_id,
                "role": ROLE_TEACHER,
            },
            {
                "_id": 1,
                "user_id": 1,
            },
        )
    )

    timestamp = now_utc()

    rebuilt = 0

    for teacher in teachers:

        teacher_id = _uid(
            teacher.get(
                "user_id"
            )
        )

        if not teacher_id:
            continue

        _sync_teacher_scope(
            school_id,
            teacher_id,
            timestamp=timestamp,
        )

        rebuilt += 1

    return {
        "school_id": school_id,
        "teachers_rebuilt": rebuilt,
        "rebuilt_at": timestamp.isoformat(),
    }