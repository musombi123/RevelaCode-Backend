"""Business verification workflow for Biashara OS.

Business owners may submit and update their application, but only an authorized
platform administrator can grant verified, active workspace access.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError


BUSINESSES = "jumuiya_businesses"
PENDING = "pending"
NEEDS_INFORMATION = "needs_information"
VERIFIED = "verified"
REJECTED = "rejected"
PENDING_STATUS = "pending_verification"

REQUIRED_APPROVAL_CHECKS = {
    "business_details_checked",
    "owner_contact_checked",
}


def now_utc():
    return datetime.now(timezone.utc)


def _text(value, default=""):
    if value is None:
        return default
    if not isinstance(value, str):
        raise APIError("Review fields must be text.", 422, "validation_error")
    return value.strip()


def _json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _serialize_business(document):
    if not document:
        return None
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    return _json_safe(result)


def review_application(
    reviewer_user_id,
    business_id,
    *,
    decision,
    notes="",
    checks=None,
):
    """Apply an admin decision to a business awaiting verification."""
    try:
        business_oid = ObjectId(str(business_id))
    except (InvalidId, TypeError, ValueError) as exc:
        raise APIError(
            "Invalid business application ID.",
            400,
            "invalid_id",
        ) from exc

    decision = _text(decision).lower()
    notes = _text(notes)

    if decision not in {"approve", "reject", "needs_information"}:
        raise APIError(
            "Decision must be approve, reject, or needs_information.",
            422,
            "validation_error",
        )

    if len(notes) > 3000:
        raise APIError(
            "Review notes cannot exceed 3000 characters.",
            422,
            "validation_error",
        )

    if not isinstance(checks, dict):
        raise APIError(
            "checks must be a JSON object.",
            422,
            "validation_error",
        )

    businesses = collection(BUSINESSES)
    business = businesses.find_one({"_id": business_oid})

    if not business:
        raise APIError(
            "Business application not found.",
            404,
            "business_application_not_found",
        )

    verification_status = business.get("verification_status")
    status = business.get("status")

    if verification_status == VERIFIED and status == "active":
        raise APIError(
            "This business is already verified.",
            409,
            "business_already_verified",
        )

    legacy_unreviewed = status == "active" and not verification_status
    reviewable = (
        verification_status in {PENDING, NEEDS_INFORMATION}
        or status == PENDING_STATUS
        or legacy_unreviewed
    )
    if not reviewable:
        raise APIError(
            "This business is not awaiting verification review.",
            409,
            "business_application_not_reviewable",
        )

    if decision == "approve":
        missing = sorted(
            key for key in REQUIRED_APPROVAL_CHECKS
            if checks.get(key) is not True
        )
        if missing:
            raise APIError(
                "Approval requires these checks to be confirmed: "
                + ", ".join(missing) + ".",
                422,
                "verification_checks_incomplete",
            )
        new_status = "active"
        new_verification_status = VERIFIED
    elif decision == "reject":
        if not notes:
            raise APIError(
                "Review notes are required when rejecting a business.",
                422,
                "review_notes_required",
            )
        new_status = "rejected"
        new_verification_status = REJECTED
    else:
        if not notes:
            raise APIError(
                "Review notes are required when requesting more information.",
                422,
                "review_notes_required",
            )
        new_status = PENDING_STATUS
        new_verification_status = NEEDS_INFORMATION

    now = now_utc()
    reviewer = str(reviewer_user_id or "").strip()
    if not reviewer:
        raise APIError(
            "Unable to identify the authenticated reviewer.",
            401,
            "authentication_required",
        )

    update = {
        "status": new_status,
        "verification_status": new_verification_status,
        "review_notes": notes,
        "reviewed_at": now,
        "reviewed_by_user_id": reviewer,
        "updated_at": now,
    }
    if decision == "approve":
        update.update({
            "verified_at": now,
            "verified_by_user_id": reviewer,
            "verification_checks": {
                key: True for key in REQUIRED_APPROVAL_CHECKS
            },
        })
    elif decision == "reject":
        update.update({
            "rejected_at": now,
            "rejected_by_user_id": reviewer,
        })

    # Compare-and-set the state observed above so two simultaneous reviewers
    # cannot both decide the same application from a stale state.
    guard = [
        {"_id": business_oid},
        {"verification_status": verification_status}
        if verification_status is not None
        else {"verification_status": {"$exists": False}},
        {"status": status}
        if status is not None
        else {"status": {"$exists": False}},
    ]
    reviewed = businesses.find_one_and_update(
        {"$and": guard},
        {
            "$set": update,
            "$push": {
                "verification_history": {
                    "event": decision,
                    "actor_user_id": reviewer,
                    "notes": notes,
                    "checks": checks if decision == "approve" else {},
                    "at": now,
                }
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not reviewed:
        raise APIError(
            "This business application changed while it was being reviewed. Refresh and try again.",
            409,
            "business_application_conflict",
        )

    log_action(
        reviewer,
        f"biashara.business.verification.{decision}",
        "business",
        business_oid,
        {"name": business.get("name", ""), "notes": notes},
    )

    return _serialize_business(reviewed)
