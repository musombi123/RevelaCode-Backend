# backend/jumuiya/elimu/school_verification.py

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.models import school_document


SCHOOLS = "jumuiya_schools"

PENDING = "pending"
NEEDS_INFORMATION = "needs_information"
VERIFIED = "verified"
REJECTED = "rejected"
DEMO = "demo"

PENDING_STATUS = "pending_verification"

# All three checks are required before a real school is approved.
REQUIRED_APPROVAL_CHECKS = {
    "registry_record_checked",
    "evidence_checked",
    "contact_independently_verified",
}


def now_utc():
    return datetime.now(timezone.utc)


def _text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _normalise_registration_number(value):
    """Ignore spaces and letter case when matching a registration number."""
    return re.sub(r"\s+", "", _text(value)).upper()


def _serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _serialize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_serialize_value(item) for item in value]

    return value


def _serialize_school(document, *, include_owner=False):
    if not document:
        return None

    output = dict(document)

    if "_id" in output:
        output["id"] = str(output.pop("_id"))

    if not include_owner:
        output.pop("owner_user_id", None)

    return _serialize_value(output)


def demo_mode_enabled():
    """
    Demo schools are permitted only when both conditions are true:

    1. ELIMU_ALLOW_DEMO_SCHOOLS=true
    2. The application explicitly identifies itself as a development,
       local, or testing environment.

    An ordinary production deployment must not enable demo access.
    """
    enabled = (
        os.getenv("ELIMU_ALLOW_DEMO_SCHOOLS", "").strip().lower()
        == "true"
    )

    environment = (
        os.getenv("APP_ENV")
        or os.getenv("FLASK_ENV")
        or os.getenv("ENVIRONMENT")
        or "production"
    ).strip().lower()

    allowed_environments = {
        "development",
        "dev",
        "local",
        "test",
        "testing",
    }

    return enabled and environment in allowed_environments


def _real_school_for_owner(user_id):
    return collection(SCHOOLS).find_one(
        {
            "owner_user_id": str(user_id),
            "is_demo": {"$ne": True},
        },
        sort=[
            ("updated_at", -1),
            ("created_at", -1),
        ],
    )


def _application_for_owner(user_id):
    """Prefer a real application; expose demos only in demo-enabled environments."""
    real_school = _real_school_for_owner(user_id)

    if real_school:
        return real_school

    if demo_mode_enabled():
        return collection(SCHOOLS).find_one(
            {
                "owner_user_id": str(user_id),
                "is_demo": True,
                "verification_status": DEMO,
                "status": "active",
            },
            sort=[("updated_at", -1)],
        )

    return None


def _is_verified_school(document):
    return bool(
        document
        and document.get("status") == "active"
        and document.get("verification_status") == VERIFIED
        and document.get("is_demo") is not True
    )


def _registration_match_query(registration_number):
    normalized = _normalise_registration_number(
        registration_number
    )

    # This also allows matching older records that do not yet have the
    # normalised field stored.
    pattern = r"^\s*" + r"\s*".join(
        re.escape(character) for character in normalized
    ) + r"\s*$"

    return {
        "is_demo": {"$ne": True},
        "status": {"$nin": ["rejected", "archived"]},
        "$or": [
            {"registration_number_normalized": normalized},
            {
                "registration_number": {
                    "$regex": pattern,
                    "$options": "i",
                }
            },
        ],
    }


def _ensure_registration_index():
    """
    Enforce uniqueness for real registration applications at the database
    level as well as through the application-level duplicate check.

    The partial index excludes demo schools.
    """
    try:
        collection(SCHOOLS).create_index(
            [("registration_number_normalized", 1)],
            unique=True,
            partialFilterExpression={
                "is_demo": False,
                "registration_number_normalized": {
                    "$type": "string",
                },
            },
            name="elimu_unique_real_school_registration",
        )
    except Exception as exc:
        # Fail closed: don't accept a new application if the uniqueness
        # protection cannot be established.
        raise APIError(
            (
                "School registration checks are temporarily unavailable. "
                "Conflicting registration records may need administrator review."
            ),
            503,
            "school_registration_index_unavailable",
        ) from exc


def _ensure_no_duplicate_registration(
    registration_number,
    *,
    exclude_id=None,
):
    query = _registration_match_query(
        registration_number
    )

    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}

    duplicate = collection(SCHOOLS).find_one(query)

    if duplicate:
        raise APIError(
            (
                "This school registration number is already associated "
                "with another application or school."
            ),
            409,
            "school_registration_exists",
        )


def get_my_application(user_id):
    """
    Return the owner's current school record, including pending applications.

    This endpoint does not grant access to the Elimu dashboard.
    Dashboard access is checked independently by access_status().
    """
    document = _application_for_owner(user_id)

    return _serialize_school(document)


def submit_application(user_id, data):
    """
    Create or resubmit an application.

    Crucially, client-supplied status, verification_status, is_demo,
    verified_by_user_id and similar fields are never used to grant access.
    """
    uid = str(user_id)
    payload = dict(data or {})
    now = now_utc()

    registration_number = _text(
        payload.get("registration_number")
    )

    if not registration_number:
        raise APIError(
            "A school registration number is required.",
            422,
            "validation_error",
        )

    if not _text(payload.get("registration_evidence_url")):
        raise APIError(
            "Registration evidence is required.",
            422,
            "validation_error",
        )

    existing = _real_school_for_owner(uid)

    if _is_verified_school(existing):
        raise APIError(
            (
                "This account already owns a verified school. "
                "School identity changes require a separate review."
            ),
            409,
            "school_already_verified",
        )

    # Create the index before accepting a real registration application.
    _ensure_registration_index()

    _ensure_no_duplicate_registration(
        registration_number,
        exclude_id=existing.get("_id") if existing else None,
    )

    # school_document() is the existing model constructor. Its default
    # active status is deliberately overridden below.
    document = school_document(uid, payload)

    document.update({
        "owner_user_id": uid,
        "registration_number": registration_number,
        "registration_number_normalized": (
            _normalise_registration_number(registration_number)
        ),
        "registration_evidence_url": _text(
            payload.get("registration_evidence_url")
        ),
        "owner_declaration": True,
        "owner_declaration_at": now,
        "submitted_at": now,
        "verification_status": PENDING,
        "status": PENDING_STATUS,
        "is_demo": False,
        "review_notes": "",
        "updated_at": now,
    })

    # Preserve creation history when the owner corrects or resubmits
    # an application that hasn't been verified.
    if existing:
        document["created_at"] = existing.get("created_at", now)

        update = collection(SCHOOLS).find_one_and_update(
            {
                "_id": existing["_id"],
                "owner_user_id": uid,
                "is_demo": {"$ne": True},
                "verification_status": {"$ne": VERIFIED},
            },
            {
                "$set": document,
                "$unset": {
                    "verified_at": "",
                    "verified_by_user_id": "",
                    "rejected_at": "",
                    "rejected_by_user_id": "",
                },
                "$push": {
                    "verification_history": {
                        "event": "resubmitted",
                        "actor_user_id": uid,
                        "at": now,
                    }
                },
            },
            return_document=ReturnDocument.AFTER,
        )

        if not update:
            raise APIError(
                "The school application changed while you were editing it.",
                409,
                "school_application_conflict",
            )

        log_action(
            uid,
            "elimu.school.application.resubmitted",
            "school",
            update["_id"],
        )

        return _serialize_school(update)

    document["verification_history"] = [
        {
            "event": "submitted",
            "actor_user_id": uid,
            "at": now,
        }
    ]

    result = collection(SCHOOLS).insert_one(document)
    document["_id"] = result.inserted_id

    log_action(
        uid,
        "elimu.school.application.submitted",
        "school",
        result.inserted_id,
        {
            "verification_status": PENDING,
        },
    )

    return _serialize_school(document)


def create_demo_school(user_id, data):
    """
    Development-only demo school creation.

    Demo status is set by the server, never accepted from the client.
    """
    if not demo_mode_enabled():
        raise APIError(
            "Demo schools are disabled in this environment.",
            403,
            "demo_schools_disabled",
        )

    uid = str(user_id)
    now = now_utc()

    real_school = _real_school_for_owner(uid)

    if real_school:
        raise APIError(
            (
                "This account already has a real school application. "
                "Use that application's verification process."
            ),
            409,
            "real_school_application_exists",
        )

    existing_demo = collection(SCHOOLS).find_one({
        "owner_user_id": uid,
        "is_demo": True,
    })

    document = school_document(uid, dict(data or {}))

    document.update({
        "owner_user_id": uid,
        "registration_number": "",
        "registration_number_normalized": "",
        "verification_status": DEMO,
        "status": "active",
        "is_demo": True,
        "demo_notice": "DEMO SCHOOL — NOT VERIFIED",
        "updated_at": now,
    })

    if existing_demo:
        document["created_at"] = existing_demo.get("created_at", now)

        updated = collection(SCHOOLS).find_one_and_update(
            {
                "_id": existing_demo["_id"],
                "owner_user_id": uid,
                "is_demo": True,
            },
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            uid,
            "elimu.school.demo.updated",
            "school",
            updated["_id"],
        )

        return _serialize_school(updated)

    document["created_at"] = now
    result = collection(SCHOOLS).insert_one(document)
    document["_id"] = result.inserted_id

    log_action(
        uid,
        "elimu.school.demo.created",
        "school",
        result.inserted_id,
    )

    return _serialize_school(document)


def access_status(user_id):
    """
    The backend is the source of truth for access.

    Legacy active schools without verification metadata are NOT implicitly
    trusted; they are presented for review instead.
    """
    document = _real_school_for_owner(user_id)

    if _is_verified_school(document):
        return {
            "allowed": True,
            "has_school": True,
            "school": _serialize_school(document),
            "verification_status": VERIFIED,
            "redirect": None,
        }

    if not document and demo_mode_enabled():
        demo = collection(SCHOOLS).find_one({
            "owner_user_id": str(user_id),
            "is_demo": True,
            "verification_status": DEMO,
            "status": "active",
        })

        if demo:
            return {
                "allowed": True,
                "has_school": True,
                "school": _serialize_school(demo),
                "verification_status": DEMO,
                "demo_mode": True,
                "redirect": None,
            }

    if not document:
        return {
            "allowed": False,
            "has_school": False,
            "school": None,
            "reason": "school_required",
            "redirect": {
                "screen": "elimu-school-setup",
                "mode": "create",
            },
        }

    verification_status = document.get("verification_status")
    school_status = document.get("status")

    # Legacy active records that have never been reviewed are treated as
    # unverified and appear in the review queue.
    if (
        school_status == "active"
        and not verification_status
    ):
        verification_status = PENDING

    if (
        verification_status == REJECTED
        or school_status == "rejected"
    ):
        return {
            "allowed": False,
            "has_school": True,
            "school": _serialize_school(document),
            "verification_status": REJECTED,
            "reason": "school_verification_rejected",
            "redirect": {
                "screen": "elimu-school-setup",
                "mode": "resubmit",
            },
        }

    if school_status == "suspended":
        return {
            "allowed": False,
            "has_school": True,
            "school": _serialize_school(document),
            "reason": "school_suspended",
            "redirect": {
                "screen": "elimu-school-verification-pending",
                "mode": "contact_support",
            },
        }

    return {
        "allowed": False,
        "has_school": True,
        "school": _serialize_school(document),
        "verification_status": verification_status or PENDING,
        "reason": "school_verification_pending",
        "redirect": {
            "screen": "elimu-school-verification-pending",
            "mode": "status",
        },
    }


def require_accessible_school(user_id):
    """
    Return the raw school document only if the owner is allowed to use Elimu.
    Used by services.py as the common backend access boundary.
    """
    uid = str(user_id)

    conditions = [
        {"verification_status": VERIFIED, "is_demo": {"$ne": True}},
    ]

    if demo_mode_enabled():
        conditions.append({
            "verification_status": DEMO,
            "is_demo": True,
        })

    school = collection(SCHOOLS).find_one({
        "owner_user_id": uid,
        "status": "active",
        "$or": conditions,
    })

    if not school:
        raise APIError(
            "A verified school account is required to access the Elimu hub.",
            403,
            "school_required",
        )

    return school


def pending_applications(limit=50):
    """Admin-only review queue, including legacy active records not yet reviewed."""
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 50

    query = {
        "is_demo": {"$ne": True},
        "$or": [
            {"status": PENDING_STATUS},
            {
                "verification_status": {
                    "$in": [PENDING, NEEDS_INFORMATION],
                }
            },
            {
                "status": "active",
                "verification_status": {"$exists": False},
            },
        ],
    }

    documents = list(
        collection(SCHOOLS)
        .find(query)
        .sort([
            ("submitted_at", 1),
            ("created_at", 1),
        ])
        .limit(limit)
    )

    return {
        "applications": [
            _serialize_school(document, include_owner=True)
            for document in documents
        ],
        "count": len(documents),
        "limit": limit,
    }


def review_application(
    reviewer_user_id,
    application_id,
    *,
    decision,
    notes="",
    checks=None,
):
    """
    Apply a verification decision after the protected route has confirmed
    that the requester has an authorised platform-administrator role.
    """
    try:
        application_oid = ObjectId(str(application_id))
    except (InvalidId, TypeError, ValueError) as exc:
        raise APIError(
            "Invalid school application ID.",
            400,
            "invalid_id",
        ) from exc

    decision = _text(decision).lower()
    notes = _text(notes)

    if len(notes) > 3000:
        raise APIError(
            "Review notes cannot exceed 3000 characters.",
            422,
            "validation_error",
        )

    if decision not in {"approve", "reject", "needs_information"}:
        raise APIError(
            "Decision must be approve, reject, or needs_information.",
            422,
            "validation_error",
        )

    if checks is None:
        checks = {}

    if not isinstance(checks, dict):
        raise APIError(
            "checks must be a JSON object.",
            422,
            "validation_error",
        )

    document = collection(SCHOOLS).find_one({
        "_id": application_oid,
        "is_demo": {"$ne": True},
    })

    if not document:
        raise APIError(
            "School application not found.",
            404,
            "school_application_not_found",
        )

    if _is_verified_school(document):
        raise APIError(
            "This school is already verified.",
            409,
            "school_already_verified",
        )

    is_legacy_unreviewed = (
        document.get("status") == "active"
        and not document.get("verification_status")
    )

    reviewable = (
        document.get("status") == PENDING_STATUS
        or document.get("verification_status") in {
            PENDING,
            NEEDS_INFORMATION,
        }
        or is_legacy_unreviewed
    )

    if not reviewable:
        raise APIError(
            "This application is not awaiting review.",
            409,
            "school_application_not_reviewable",
        )

    now = now_utc()
    reviewer = str(reviewer_user_id)

    if decision == "approve":
        missing_checks = [
            key
            for key in REQUIRED_APPROVAL_CHECKS
            if checks.get(key) is not True
        ]

        if missing_checks:
            raise APIError(
                (
                    "Approval requires all verification checks to be "
                    f"confirmed: {', '.join(sorted(missing_checks))}."
                ),
                422,
                "verification_checks_incomplete",
            )

        if not _text(document.get("registration_evidence_url")):
            raise APIError(
                (
                    "The application has no registration evidence. "
                    "Request the owner to supply evidence before approval."
                ),
                422,
                "registration_evidence_missing",
            )

        _ensure_registration_index()
        _ensure_no_duplicate_registration(
            document.get("registration_number", ""),
            exclude_id=document["_id"],
        )

        new_status = "active"
        new_verification_status = VERIFIED

    elif decision == "reject":
        new_status = "rejected"
        new_verification_status = REJECTED

    else:
        new_status = PENDING_STATUS
        new_verification_status = NEEDS_INFORMATION

    update = {
        "status": new_status,
        "verification_status": new_verification_status,
        "review_notes": notes,
        "reviewed_at": now,
        "reviewer_user_id": reviewer,
        "updated_at": now,
    }

    if decision == "approve":
        update.update({
            "verified_at": now,
            "verified_by_user_id": reviewer,
            "verification_checks": {
                key: True
                for key in REQUIRED_APPROVAL_CHECKS
            },
        })

    if decision == "reject":
        update.update({
            "rejected_at": now,
            "rejected_by_user_id": reviewer,
        })

    reviewed = collection(SCHOOLS).find_one_and_update(
        {
            "_id": application_oid,
            "is_demo": {"$ne": True},
        },
        {
            "$set": update,
            "$push": {
                "verification_history": {
                    "event": decision,
                    "actor_user_id": reviewer,
                    "notes": notes,
                    "at": now,
                }
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        reviewer,
        f"elimu.school.verification.{decision}",
        "school",
        application_oid,
        {
            "registration_number": document.get(
                "registration_number",
                "",
            ),
            "notes": notes,
        },
    )

    return _serialize_school(
        reviewed,
        include_owner=True,
    )