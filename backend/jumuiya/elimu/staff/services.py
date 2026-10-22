# backend/jumuiya/elimu/staff/services.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Mapping

from bson import ObjectId

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import (
    ROLE_OWNER,
    ROLE_PRINCIPAL,
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

from .invitation_email import send_staff_invitation_email


CHANGE_REQUESTS = "jumuiya_elimu_staff_change_requests"


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
        "email_sent_at",
        "requested_at",
        "decided_at",
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


def _notify_user(user_id: Any, *, title: str, message: str, kind: str, data: dict | None = None) -> None:
    """Best-effort in-app notification using the shared Jumuiya notification store."""
    if not _uid(user_id):
        return
    try:
        from backend.jumuiya.notifications.services import notify

        notify(_uid(user_id), {
            "title": title,
            "message": message,
            "type": kind,
            "data": data or {},
        })
    except Exception:
        # A notification outage must not undo a committed staff change/request.
        logging.exception("Elimu staff notification failed for user %s", _uid(user_id))


def _owner_for_school(school_id: str) -> str:
    school = _school_document(school_id) or {}
    return _uid(school.get("owner_user_id") or school.get("owner_id"))


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
# INVITATION DELIVERY / SERIALIZATION
# =========================================================

def _school_document(school_id: str) -> dict | None:
    conditions = [
        {"_id": school_id},
        {"school_id": school_id},
    ]
    if ObjectId.is_valid(school_id):
        conditions.append({"_id": ObjectId(school_id)})
    return collection(SCHOOLS).find_one({"$or": conditions})


def _display_name(document: Mapping[str, Any] | None) -> str:
    if not isinstance(document, Mapping):
        return ""
    identity = document.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    for value in (
        identity.get("display_name"),
        identity.get("preferred_name"),
        document.get("display_name"),
        document.get("full_name"),
        document.get("name"),
        identity.get("email"),
        document.get("email"),
    ):
        normalized = normalize_text(value)
        if normalized:
            return normalized
    return ""


def _invitation_snapshot(document: Mapping[str, Any] | None) -> dict:
    """Return only safe invitation fields; never expose the token or its hash."""
    data = _ser(dict(document)) if isinstance(document, Mapping) else {}
    data = data or {}
    profile = data.get("profile") if isinstance(data.get("profile"), Mapping) else {}
    identity = profile.get("identity") if isinstance(profile.get("identity"), Mapping) else {}
    invitation_id = data.get("_id") or data.get("id") or data.get("invitation_id")
    return {
        "_id": str(invitation_id or ""),
        "id": str(invitation_id or ""),
        "school_id": data.get("school_id"),
        "email": data.get("email"),
        "display_name": identity.get("display_name") or identity.get("preferred_name") or "",
        "role": data.get("role"),
        "status": data.get("status"),
        "email_status": data.get("email_status", "pending"),
        "email_error": data.get("email_error"),
        "email_error_code": data.get("email_error_code"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "expires_at": data.get("expires_at"),
        "email_sent_at": data.get("email_sent_at"),
        "accepted_at": data.get("accepted_at"),
        "cancelled_at": data.get("cancelled_at"),
        "invited_by": data.get("invited_by"),
        "accepted_by": data.get("accepted_by"),
    }


def _deliver_invitation_email(
    school_id: str,
    invitation: dict,
    raw_token: str,
) -> bool:
    """Deliver the one-time link without returning the raw token to the browser."""
    timestamp = now_utc()
    invitation_id = invitation.get("_id")
    target = {"_id": invitation_id, "school_id": school_id}
    collection(INVITATIONS).update_one(
        target,
        {"$set": {"email_status": "pending", "updated_at": timestamp}},
    )
    invitation["email_status"] = "pending"
    invitation["updated_at"] = timestamp

    school = _school_document(school_id) or {}
    inviter = _find_staff(
        school_id,
        invitation.get("invited_by"),
        include_removed=True,
    )
    profile = invitation.get("profile") if isinstance(invitation.get("profile"), Mapping) else {}
    identity = profile.get("identity") if isinstance(profile.get("identity"), Mapping) else {}
    inviter_identity = (inviter or {}).get("identity") if isinstance((inviter or {}).get("identity"), Mapping) else {}
    school_name = (
        school.get("name")
        or school.get("school_name")
        or school.get("institution_name")
        or "your school"
    )
    inviter_email = inviter_identity.get("email") or (inviter or {}).get("email") or ""

    try:
        send_staff_invitation_email(
            recipient=invitation.get("email", ""),
            invitee_name=identity.get("display_name") or identity.get("preferred_name") or "",
            school_name=school_name,
            inviter_name=_display_name(inviter) or "the school owner",
            inviter_email=inviter_email,
            role=invitation.get("role", ""),
            token=raw_token,
            expires_at=invitation.get("expires_at"),
        )
    except Exception as exc:
        detail = str(exc).lower()
        error_code = "resend_delivery_rejected"
        message = "Resend rejected the invitation email. Check the backend logs and Resend email logs, then retry."
        if "resend_api_key is not configured" in detail:
            error_code = "missing_resend_api_key"
            message = "RESEND_API_KEY is missing from the backend environment."
        elif "resend sdk is not installed" in detail or "no module named 'resend'" in detail:
            error_code = "resend_sdk_missing"
            message = "The Resend SDK is missing from the backend deployment. Rebuild the backend before retrying."
        elif "frontend_url" in detail or "revelacode_frontend_url" in detail:
            error_code = "invalid_frontend_url"
            message = "FRONTEND_URL must point to the public HTTPS RevelaCode frontend."
        elif "email_from is not configured" in detail:
            error_code = "missing_email_from"
            message = "EMAIL_FROM is empty. Configure an authorised sender address."
        elif any(term in detail for term in ("unauthorized", "invalid api key", "authentication failed", "status code 401", "http 401")):
            error_code = "resend_api_key_rejected"
            message = "Resend rejected the API key. Check RESEND_API_KEY in the backend service settings."
        elif any(term in detail for term in ("domain is not verified", "domain not verified", "sender not verified", "only send testing emails to your own email", "not authorized to send", "from address")):
            error_code = "sender_not_authorised"
            message = "Resend did not authorise the sender or recipient. Verify the sending domain and use an address on that domain."
        logging.getLogger(__name__).warning(
            "Elimu invitation email failure: invitation_id=%s error_code=%s exception_type=%s",
            str(invitation_id),
            error_code,
            type(exc).__name__,
        )
        collection(INVITATIONS).update_one(
            target,
            {
                "$set": {
                    "email_status": "failed",
                    "email_error": message,
                    "email_error_code": error_code,
                    "updated_at": now_utc(),
                },
                "$unset": {"email_sent_at": ""},
            },
        )
        invitation["email_status"] = "failed"
        invitation["email_error"] = message
        invitation["email_error_code"] = error_code
        invitation.pop("email_sent_at", None)
        return False

    sent_at = now_utc()
    collection(INVITATIONS).update_one(
        target,
        {
            "$set": {
                "email_status": "sent",
                "email_sent_at": sent_at,
                "updated_at": sent_at,
            },
            "$unset": {"email_error": "", "email_error_code": ""},
        },
    )
    invitation["email_status"] = "sent"
    invitation["email_sent_at"] = sent_at
    invitation["updated_at"] = sent_at
    invitation.pop("email_error", None)
    invitation.pop("email_error_code", None)
    return True


def _find_invitation(school_id: str, invitation_id: Any) -> dict | None:
    normalized_id = _uid(invitation_id)
    if not normalized_id:
        return None
    conditions = [{"_id": normalized_id}, {"invitation_id": normalized_id}]
    if ObjectId.is_valid(normalized_id):
        conditions.insert(0, {"_id": ObjectId(normalized_id)})
    return collection(INVITATIONS).find_one({"school_id": school_id, "$or": conditions})

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

    # Only the School Owner may appoint the single designated Principal.
    # This applies to both email invitations and direct links to an existing account.
    if role == ROLE_PRINCIPAL:
        inviter_role = normalize_text(member.get("role")).lower()
        if inviter_role != ROLE_OWNER:
            raise APIError(
                "Only the School Owner can appoint the school's designated Principal.",
                403,
                "principal_owner_required",
            )

        existing_principal = collection(STAFF_COLLECTION).find_one({
            "school_id": school_id,
            "role": ROLE_PRINCIPAL,
            "status": {"$nin": ["removed", "suspended"]},
        })
        pending_principal = None
        for candidate in collection(INVITATIONS).find({
            "school_id": school_id,
            "role": ROLE_PRINCIPAL,
            "status": "invited",
        }).limit(500):
            if invitation_is_usable(candidate):
                pending_principal = candidate
                break
        if existing_principal or pending_principal:
            raise APIError(
                "This school already has a Principal or a valid pending Principal invitation. Revoke the pending invitation or resolve the existing membership before appointing another.",
                409,
                "principal_already_assigned",
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

    email_sent = _deliver_invitation_email(
        school_id,
        document,
        raw_token,
    )

    return {
        "mode": "email_invitation",
        "invitation": _invitation_snapshot(document),
        "email_sent": email_sent,
    }


# =========================================================
# INVITATION MANAGEMENT
# =========================================================

def list_invitations(user_id: Any) -> dict:
    member = authorize(user_id, "staff.view")
    school_id = _school_id(member)
    documents = list(
        collection(INVITATIONS)
        .find({"school_id": school_id})
        .sort("created_at", -1)
        .limit(200)
    )
    invitations = [_invitation_snapshot(document) for document in documents]
    return {"school_id": school_id, "count": len(invitations), "invitations": invitations}


def resend_invitation(user_id: Any, invitation_id: Any) -> dict:
    member = authorize(user_id, "staff.invite")
    school_id = _school_id(member)
    document = _find_invitation(school_id, invitation_id)
    if not document or normalize_text(document.get("status")).lower() != "invited":
        raise APIError("Pending invitation not found.", 404, "invitation_not_found")

    timestamp = now_utc()
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_invitation_token(raw_token)
    expires_at = timestamp + timedelta(days=7)
    result = collection(INVITATIONS).update_one(
        {"_id": document["_id"], "school_id": school_id, "status": "invited"},
        {
            "$set": {
                "token_hash": token_hash,
                "expires_at": expires_at,
                "email_status": "pending",
                "updated_at": timestamp,
            },
            "$unset": {"email_error": "", "email_error_code": "", "email_sent_at": ""},
        },
    )
    if not result.matched_count:
        raise APIError("Invitation changed before it could be resent. Refresh and try again.", 409, "invitation_changed")

    document["token_hash"] = token_hash
    document["expires_at"] = expires_at
    document["email_status"] = "pending"
    document["updated_at"] = timestamp
    document.pop("email_error", None)
    document.pop("email_error_code", None)
    document.pop("email_sent_at", None)
    email_sent = _deliver_invitation_email(school_id, document, raw_token)
    return {"invitation": _invitation_snapshot(document), "email_sent": email_sent}


def revoke_invitation(user_id: Any, invitation_id: Any) -> dict:
    member = authorize(user_id, "staff.invite")
    school_id = _school_id(member)
    document = _find_invitation(school_id, invitation_id)
    if not document or normalize_text(document.get("status")).lower() != "invited":
        raise APIError("Pending invitation not found.", 404, "invitation_not_found")

    timestamp = now_utc()
    result = collection(INVITATIONS).update_one(
        {"_id": document["_id"], "school_id": school_id, "status": "invited"},
        {"$set": {"status": "cancelled", "cancelled_at": timestamp, "updated_at": timestamp}},
    )
    if not result.matched_count:
        raise APIError("Invitation changed before it could be revoked. Refresh and try again.", 409, "invitation_changed")
    document["status"] = "cancelled"
    document["cancelled_at"] = timestamp
    document["updated_at"] = timestamp
    return {"invitation": _invitation_snapshot(document), "revoked": True}

# =========================================================
# OWNER-APPROVED STAFF CHANGE REQUESTS
# =========================================================

def list_staff_change_requests(user_id: Any) -> dict:
    member = authorize(user_id, "staff.view")
    school_id = _school_id(member)
    documents = list(
        collection(CHANGE_REQUESTS)
        .find({"school_id": school_id})
        .sort("requested_at", -1)
        .limit(200)
    )
    return {
        "school_id": school_id,
        "count": len(documents),
        "requests": [_ser(document) for document in documents],
    }


def request_staff_change(user_id: Any, staff_user_id: Any, payload: dict) -> dict:
    requester = authorize(user_id, "staff.update")
    requester_role = normalize_text(requester.get("role")).lower()
    if requester_role != ROLE_PRINCIPAL:
        raise APIError(
            "Only the Principal/Headteacher may submit a staff transfer for owner approval.",
            403,
            "principal_change_request_required",
        )

    school_id = _school_id(requester)
    target_user_id = _uid(staff_user_id)
    target = _require_staff(school_id, target_user_id)
    _protect_owner(target)

    if not isinstance(payload, dict):
        raise APIError("A JSON object is required.", 422, "validation_error")

    change_type = normalize_text(payload.get("change_type") or "transfer").lower()
    notes = normalize_text(payload.get("notes"))
    if len(notes) > 1000:
        raise APIError("notes must not exceed 1000 characters.", 422, "validation_error")

    requested_changes = {}
    if change_type == "transfer":
        raw_employment = payload.get("employment") or {}
        if not isinstance(raw_employment, dict):
            raise APIError("employment must be an object.", 422, "validation_error")
        employment = {}
        for key in ("department", "store"):
            if key in raw_employment:
                value = normalize_text(raw_employment.get(key))
                if len(value) > 160:
                    raise APIError(f"{key} must not exceed 160 characters.", 422, "validation_error")
                employment[key] = value or None
        if employment:
            requested_changes["employment"] = employment

        if "assigned_class_ids" in payload:
            class_ids = normalize_class_ids(payload.get("assigned_class_ids"))
            if class_ids and normalize_text(target.get("role")).lower() != ROLE_TEACHER:
                raise APIError("Only a teacher can be assigned to classes.", 422, "teacher_class_scope_invalid")
            for class_id in class_ids:
                _require_school_class(school_id, class_id)
            requested_changes["assigned_class_ids"] = class_ids
        if not requested_changes:
            raise APIError("Specify a new department, store, or teacher class assignment.", 422, "empty_staff_change")
    elif change_type == "remove":
        requested_changes = {}
    else:
        raise APIError("change_type must be transfer or remove.", 422, "invalid_staff_change_type")

    now = now_utc()
    document = {
        "school_id": school_id,
        "staff_user_id": target_user_id,
        "staff_name": _display_name(target),
        "staff_role": normalize_text(target.get("role")).lower(),
        "change_type": change_type,
        "requested_changes": requested_changes,
        "notes": notes,
        "requested_by_user_id": _uid(user_id),
        "requester_role": requester_role,
        "status": "pending",
        "requested_at": now,
        "created_at": now,
        "updated_at": now,
    }
    result = collection(CHANGE_REQUESTS).insert_one(document)
    document["_id"] = result.inserted_id

    owner_id = _owner_for_school(school_id)
    label = "removal" if change_type == "remove" else "transfer"
    _notify_user(
        owner_id,
        title=f"Staff {label} awaiting approval",
        message=f"{_display_name(target) or target_user_id} has a pending staff {label} request from the Principal/Headteacher.",
        kind="action_needed",
        data={"school_id": school_id, "request_id": str(result.inserted_id), "staff_user_id": target_user_id},
    )
    return {"approval_required": True, "request": _ser(document)}


def decide_staff_change_request(user_id: Any, request_id: Any, payload: dict) -> dict:
    member = authorize(user_id, "staff.update")
    if normalize_text(member.get("role")).lower() != ROLE_OWNER:
        raise APIError("Only the School Owner/Director can approve or reject staff change requests.", 403, "owner_approval_required")

    school_id = _school_id(member)
    try:
        request_oid = ObjectId(str(request_id))
    except Exception:
        request_oid = str(request_id)

    request_doc = collection(CHANGE_REQUESTS).find_one({
        "_id": request_oid,
        "school_id": school_id,
    })
    if not request_doc or request_doc.get("status") != "pending":
        raise APIError("Pending staff change request not found.", 404, "staff_change_request_not_found")

    decision = normalize_text((payload or {}).get("decision")).lower()
    notes = normalize_text((payload or {}).get("notes"))
    if decision not in {"approve", "reject"}:
        raise APIError("decision must be approve or reject.", 422, "invalid_staff_change_decision")
    if len(notes) > 1000:
        raise APIError("notes must not exceed 1000 characters.", 422, "validation_error")

    target_id = _uid(request_doc.get("staff_user_id"))
    if decision == "approve":
        if request_doc.get("change_type") == "remove":
            remove_staff(user_id, target_id)
        elif request_doc.get("change_type") == "transfer":
            update_staff(user_id, target_id, request_doc.get("requested_changes") or {})
        else:
            raise APIError("Unsupported staff change request type.", 422, "invalid_staff_change_type")

    now = now_utc()
    status = "approved" if decision == "approve" else "rejected"
    updated = collection(CHANGE_REQUESTS).find_one_and_update(
        {"_id": request_doc["_id"], "school_id": school_id, "status": "pending"},
        {"$set": {
            "status": status,
            "decision": decision,
            "decision_notes": notes,
            "decided_by_user_id": _uid(user_id),
            "decided_at": now,
            "updated_at": now,
        }},
        return_document=__import__("pymongo").ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError("Request was changed by another reviewer. Refresh and retry.", 409, "staff_change_request_changed")

    requester_id = _uid(request_doc.get("requested_by_user_id"))
    _notify_user(
        requester_id,
        title=f"Staff {request_doc.get('change_type', 'change')} request {status}",
        message=f"The School Owner has {status} your request for {request_doc.get('staff_name') or target_id}." + (f" Notes: {notes}" if notes else ""),
        kind="success" if decision == "approve" else "warning",
        data={"school_id": school_id, "request_id": str(request_doc["_id"]), "decision": decision},
    )
    return {"request": _ser(updated), "applied": decision == "approve"}


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

    requester_role = normalize_text(member.get("role")).lower()
    if requester_role == ROLE_PRINCIPAL:
        return request_staff_change(
            user_id,
            target_user_id,
            {
                "change_type": "remove",
                "notes": "Removal requested by the Principal/Headteacher.",
            },
        )
    if requester_role != ROLE_OWNER:
        raise APIError(
            "Only the Principal/Headteacher may request removal; only the School Owner may execute it.",
            403,
            "staff_removal_role_denied",
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
    user_email: str | None = None,
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

    invited_email = normalize_text(invitation.get("email")).lower()
    authenticated_email = normalize_text(user_email).lower()
    if not authenticated_email or authenticated_email != invited_email:
        raise APIError(
            "Sign in with the verified email address this invitation was sent to.",
            403,
            "invitation_email_mismatch",
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