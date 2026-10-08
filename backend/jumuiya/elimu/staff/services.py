# backend/jumuiya/elimu/staff/services.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
    hash_invitation_token,
    invitation_doc,
    invitation_is_usable,
    membership_doc,
)


# =========================================================
# COLLECTIONS
# =========================================================

STAFF_COLLECTION = COLLECTION

ASSIGNMENTS = "jumuiya_elimu_teacher_assignments"

SCHOOLS = "jumuiya_schools"

CLASSES = "jumuiya_classes"


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
    member: dict,
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
        query["$or"].append(
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
        query["status"] = {
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
    staff_document: dict,
) -> None:
    target_role = str(
        staff_document.get(
            "role",
            "",
        )
    ).strip().lower()

    if target_role == ROLE_OWNER:
        raise APIError(
            "The school owner membership is protected.",
            403,
            "owner_role_protected",
        )


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

    return {
        "school_id": school_id,
        "staff": _many(
            documents
        ),
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

    return _ser(
        document
    )


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

    role = str(
        payload.get(
            "role",
            "",
        )
    ).strip().lower()

    if role == ROLE_OWNER:
        raise APIError(
            "Owner cannot be invited through staff management.",
            403,
            "owner_role_protected",
        )

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
            metadata=payload.get(
                "metadata"
            ) or {},
            activated_at=now_utc(),
        )

        collection(
            STAFF_COLLECTION
        ).insert_one(
            document
        )

        return {
            "mode": "user_link",
            "staff": _ser(
                document
            ),
        }

    # -----------------------------------------------------
    # Email invitation
    # -----------------------------------------------------

    email = str(
        payload.get(
            "email",
            "",
        )
    ).strip().lower()

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

    document["_id"] = (
        result.inserted_id
    )

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

    if target_user_id == requester_user_id:
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

    current_role = str(
        document.get(
            "role",
            "",
        )
    ).strip().lower()

    new_role = str(
        updates.get(
            "role",
            current_role,
        )
    ).strip().lower()

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
        updates["permissions"] = sorted(
            effective_permissions(
                new_role,
                updates[
                    "permissions"
                ],
            )
        )

    # -----------------------------------------------------
    # Assigned classes
    # -----------------------------------------------------

    if "assigned_class_ids" in updates:

        class_ids = [
            _uid(value)
            for value in updates.get(
                "assigned_class_ids",
                [],
            )
            if _uid(value)
        ]

        class_ids = list(
            dict.fromkeys(
                class_ids
            )
        )

        if (
            class_ids
            and new_role != ROLE_TEACHER
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

    # -----------------------------------------------------
    # Role transition away from Teacher
    # -----------------------------------------------------

    role_changed = (
        new_role != current_role
    )

    if (
        role_changed
        and current_role == ROLE_TEACHER
        and new_role != ROLE_TEACHER
    ):
        updates[
            "assigned_class_ids"
        ] = []

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

    new_status = str(
        updates.get(
            "status",
            document.get(
                "status",
                "active",
            ),
        )
    ).strip().lower()

    if new_status in {
        "suspended",
        "removed",
    }:
        updates[
            "assigned_class_ids"
        ] = []

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
    # Save
    # -----------------------------------------------------

    result = collection(
        STAFF_COLLECTION
    ).update_one(
        {
            "_id": document[
                "_id"
            ]
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

    updated = collection(
        STAFF_COLLECTION
    ).find_one(
        {
            "_id": document[
                "_id"
            ]
        }
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

    if target_user_id == requester_user_id:
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

    result = collection(
        STAFF_COLLECTION
    ).update_one(
        {
            "_id": document[
                "_id"
            ],
            "status": {
                "$ne": "removed"
            },
        },
        {
            "$set": {
                "status": "removed",
                "assigned_class_ids": [],
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

    token_hash = hash_invitation_token(
        raw_token
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
            "This invitation has expired.",
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

    if not school_id or not current_user:
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

    document = membership_doc(
        school_id=school_id,
        user_id=current_user,
        role=invitation[
            "role"
        ],
        invited_by=invitation[
            "invited_by"
        ],
        status="active",
        permissions=invitation.get(
            "permissions"
        ),
        assigned_class_ids=invitation.get(
            "assigned_class_ids"
        ),
        accepted_at=timestamp,
        activated_at=timestamp,
        metadata=invitation.get(
            "metadata"
        ) or {},
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

    document["_id"] = (
        result.inserted_id
    )

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
        # The membership was created, but the invitation was
        # already consumed by another request. The database
        # transaction/unique constraints should be strengthened
        # when we wire the final production invitation flow.
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

    # -----------------------------------------------------
    # Validate class
    # -----------------------------------------------------

    _require_school_class(
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
    # Normalize subjects
    # -----------------------------------------------------

    subjects = [
        str(value).strip()
        for value in payload.get(
            "subjects",
            [],
        )
        if str(value).strip()
    ]

    subjects = list(
        dict.fromkeys(
            subjects
        )
    )

    status = str(
        payload.get(
            "status",
            "active",
        )
    ).strip().lower()

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

    # -----------------------------------------------------
    # Assignment document
    # -----------------------------------------------------

    collection(
        ASSIGNMENTS
    ).update_one(
        {
            "school_id": school_id,
            "teacher_user_id": teacher_user_id,
            "class_id": class_id,
        },
        {
            "$set": {
                "subjects": subjects,
                "status": status,
                "updated_at": timestamp,
            },
            "$setOnInsert": {
                "school_id": school_id,
                "teacher_user_id": teacher_user_id,
                "class_id": class_id,
                "created_at": timestamp,
            },
        },
        upsert=True,
    )

    # -----------------------------------------------------
    # Keep membership class scope synchronized
    # -----------------------------------------------------

    assigned_class_ids = {
        _uid(value)
        for value in teacher.get(
            "assigned_class_ids",
            [],
        )
        if _uid(value)
    }

    if status == "active":
        assigned_class_ids.add(
            class_id
        )
    else:
        assigned_class_ids.discard(
            class_id
        )

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
                "assigned_class_ids": sorted(
                    assigned_class_ids
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

    requester_role = str(
        member.get(
            "role",
            "",
        )
    ).strip().lower()

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

    documents = (
        collection(
            ASSIGNMENTS
        )
        .find(query)
        .sort(
            "created_at",
            1,
        )
    )

    return {
        "school_id": school_id,
        "teacher_user_id": target_teacher_id,
        "assignments": _many(
            documents
        ),
    }