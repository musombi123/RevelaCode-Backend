# backend/jumuiya/elimu/inventory/services.py
"""School-scoped inventory ledger and Principal-approved supply requests."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize

ITEMS = "jumuiya_elimu_inventory_items"
MOVEMENTS = "jumuiya_elimu_inventory_movements"
NEEDS = "jumuiya_elimu_inventory_needs"
SCHOOLS = "jumuiya_schools"


def _now():
    return datetime.now(timezone.utc)


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _uid(value: Any) -> str:
    return _text(value, 160)


def _number(value: Any, field: str, *, minimum: float = 0, maximum: float = 1_000_000_000) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise APIError(f"{field} must be a number.", 422, "validation_error")
    if not isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise APIError(f"{field} must be between {minimum:g} and {maximum:g}.", 422, "validation_error")
    return parsed


def _id_candidates(value: Any) -> list[Any]:
    normalized = _uid(value)
    if not normalized:
        return []
    result = [normalized]
    if ObjectId.is_valid(normalized):
        result.append(ObjectId(normalized))
    return result


def _serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _doc(value: dict | None) -> dict | None:
    if not value:
        return None
    output = _serialize(value)
    output["id"] = str(value.get("_id") or value.get("id") or "")
    return output


def _member(user_id: Any, permission: str, role: str | None = None) -> tuple[dict, str]:
    member = authorize(user_id, permission)
    school_id = _uid(member.get("school_id"))
    if not school_id:
        raise APIError("An active school membership is required.", 403, "school_membership_required")
    if role and _text(member.get("role"), 40).lower() != role:
        raise APIError(f"Only the school {role.title()} can perform this action.", 403, "role_required")
    return member, school_id


def _owned(collection_name: str, school_id: str, record_id: Any) -> dict | None:
    candidates = _id_candidates(record_id)
    if not candidates:
        return None
    return collection(collection_name).find_one({
        "school_id": school_id,
        "_id": {"$in": candidates},
    })


def list_items(user_id: Any) -> dict:
    _, school_id = _member(user_id, "inventory.view")
    items = list(collection(ITEMS).find({"school_id": school_id}).sort([("name", 1), ("created_at", -1)]).limit(500))
    return {"items": [_doc(item) for item in items], "count": len(items)}


def create_item(user_id: Any, data: dict) -> dict:
    member, school_id = _member(user_id, "inventory.manage")
    name = _text(data.get("name"), 160)
    unit = _text(data.get("unit") or "units", 40)
    category = _text(data.get("category") or "General", 80)
    if not name:
        raise APIError("Item name is required.", 422, "validation_error")
    minimum_quantity = _number(data.get("minimum_quantity", 0), "Minimum quantity")
    opening_quantity = _number(data.get("opening_quantity", 0), "Opening quantity")
    now = _now()
    document = {
        "school_id": school_id,
        "name": name,
        "category": category,
        "unit": unit,
        "quantity": opening_quantity,
        "minimum_quantity": minimum_quantity,
        "storage_location": _text(data.get("storage_location"), 160),
        "expiry_date": _text(data.get("expiry_date"), 40),
        "notes": _text(data.get("notes"), 2000),
        "created_by_user_id": _uid(user_id),
        "updated_by_user_id": _uid(user_id),
        "created_at": now,
        "updated_at": now,
    }
    result = collection(ITEMS).insert_one(document)
    document["_id"] = result.inserted_id
    if opening_quantity > 0:
        collection(MOVEMENTS).insert_one({
            "school_id": school_id,
            "item_id": str(result.inserted_id),
            "item_name": name,
            "movement_type": "opening",
            "quantity": opening_quantity,
            "unit": unit,
            "notes": "Opening balance entered when inventory item was created.",
            "created_by_user_id": _uid(user_id),
            "created_at": now,
        })
    return {"item": _doc(document)}


def update_item(user_id: Any, item_id: Any, data: dict) -> dict:
    _, school_id = _member(user_id, "inventory.manage")
    candidates = _id_candidates(item_id)
    if not candidates:
        raise APIError("A valid item ID is required.", 422, "invalid_item_id")
    updates = {}
    for field, limit in (
        ("name", 160), ("category", 80), ("unit", 40),
        ("storage_location", 160), ("expiry_date", 40), ("notes", 2000),
    ):
        if field in data:
            updates[field] = _text(data[field], limit)
    if "minimum_quantity" in data:
        updates["minimum_quantity"] = _number(data["minimum_quantity"], "Minimum quantity")
    if not updates:
        raise APIError("At least one editable item field is required.", 422, "empty_update")
    if "name" in updates and not updates["name"]:
        raise APIError("Item name cannot be blank.", 422, "validation_error")
    updates.update({"updated_by_user_id": _uid(user_id), "updated_at": _now()})
    doc = collection(ITEMS).find_one_and_update(
        {"school_id": school_id, "_id": {"$in": candidates}},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise APIError("Inventory item was not found in this school.", 404, "inventory_item_not_found")
    return {"item": _doc(doc)}


def record_movement(user_id: Any, data: dict) -> dict:
    _, school_id = _member(user_id, "inventory.manage")
    item_id = data.get("item_id") or data.get("itemId")
    movement_type = _text(data.get("movement_type") or data.get("type"), 30).lower()
    if movement_type not in {"receive", "issue"}:
        raise APIError("Movement type must be receive or issue.", 422, "validation_error")
    quantity = _number(data.get("quantity"), "Quantity", minimum=0.000001)
    candidates = _id_candidates(item_id)
    if not candidates:
        raise APIError("A valid inventory item is required.", 422, "invalid_item_id")
    query = {"school_id": school_id, "_id": {"$in": candidates}}
    if movement_type == "issue":
        query["quantity"] = {"$gte": quantity}
    delta = quantity if movement_type == "receive" else -quantity
    item = collection(ITEMS).find_one_and_update(
        query,
        {"$inc": {"quantity": delta}, "$set": {"updated_by_user_id": _uid(user_id), "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not item:
        if not _owned(ITEMS, school_id, item_id):
            raise APIError("Inventory item was not found in this school.", 404, "inventory_item_not_found")
        raise APIError("There is not enough stock to issue that quantity.", 409, "insufficient_stock")
    movement = {
        "school_id": school_id,
        "item_id": str(item.get("_id")),
        "item_name": item.get("name", ""),
        "movement_type": movement_type,
        "quantity": quantity,
        "unit": item.get("unit", "units"),
        "notes": _text(data.get("notes"), 1000),
        "created_by_user_id": _uid(user_id),
        "created_at": _now(),
    }
    result = collection(MOVEMENTS).insert_one(movement)
    movement["_id"] = result.inserted_id
    return {"item": _doc(item), "movement": _doc(movement)}


def list_needs(user_id: Any) -> dict:
    _, school_id = _member(user_id, "inventory.view")
    needs = list(collection(NEEDS).find({"school_id": school_id}).sort([("created_at", -1)]).limit(300))
    return {"needs": [_doc(item) for item in needs], "count": len(needs)}


def create_need(user_id: Any, data: dict) -> dict:
    member, school_id = _member(user_id, "inventory.manage", "storekeeper")
    item_name = _text(data.get("item_name") or data.get("name"), 160)
    quantity = _number(data.get("quantity"), "Quantity", minimum=0.000001)
    unit = _text(data.get("unit") or "kg", 40)
    purpose = _text(data.get("purpose"), 1000)
    if not item_name:
        raise APIError("Supply item name is required (for example, maize or beans).", 422, "validation_error")
    now = _now()
    need = {
        "school_id": school_id,
        "item_name": item_name,
        "quantity": quantity,
        "unit": unit,
        "needed_by": _text(data.get("needed_by"), 40),
        "purpose": purpose,
        "notes": _text(data.get("notes"), 2000),
        "status": "pending",
        "community_post_id": "",
        "publication_status": "not_submitted",
        "publication_error": "",
        "requested_by_user_id": _uid(user_id),
        "requester_role": _text(member.get("role"), 40).lower(),
        "created_at": now,
        "updated_at": now,
    }
    result = collection(NEEDS).insert_one(need)
    need["_id"] = result.inserted_id
    return {"need": _doc(need)}


def _school_name(school_id: str) -> str:
    candidates: list[Any] = [school_id]
    if ObjectId.is_valid(school_id):
        candidates.append(ObjectId(school_id))
    school = collection(SCHOOLS).find_one({"$or": [
        {"_id": {"$in": candidates}},
        {"school_id": school_id},
    ]})
    return _text((school or {}).get("name") or (school or {}).get("school_name"), 200) or "A school"


def decide_need(user_id: Any, need_id: Any, data: dict) -> dict:
    member, school_id = _member(user_id, "inventory.manage", "principal")
    decision = _text(data.get("decision"), 20).lower()
    if decision not in {"approve", "reject"}:
        raise APIError("Decision must be approve or reject.", 422, "validation_error")
    candidates = _id_candidates(need_id)
    if not candidates:
        raise APIError("A valid supply request ID is required.", 422, "invalid_need_id")
    target = collection(NEEDS)
    current = target.find_one({"school_id": school_id, "_id": {"$in": candidates}})
    if not current:
        raise APIError("Supply request was not found in this school.", 404, "inventory_need_not_found")
    if current.get("status") == "rejected":
        raise APIError("A rejected supply request cannot be approved or published.", 409, "need_already_rejected")
    if current.get("status") == "approved" and decision == "reject":
        raise APIError("An approved supply request cannot be rejected afterward.", 409, "need_already_approved")
    if current.get("status") == "pending":
        changed = target.find_one_and_update(
            {"school_id": school_id, "_id": current["_id"], "status": "pending"},
            {"$set": {
                "status": "approved" if decision == "approve" else "rejected",
                "reviewed_by_user_id": _uid(user_id),
                "reviewed_at": _now(),
                "review_notes": _text(data.get("notes"), 1000),
                "updated_at": _now(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not changed:
            raise APIError("This request was already reviewed. Refresh the list.", 409, "need_already_reviewed")
        current = changed
    elif current.get("status") != "approved":
        raise APIError("Only pending supply requests can be reviewed.", 409, "need_not_pending")
    if decision == "reject":
        return {"need": _doc(current)}

    # Approval is persisted first. Publishing is idempotent and retryable:
    # if Community is unavailable, the request stays approved and can be retried.
    if current.get("community_post_id"):
        return {"need": _doc(current)}
    try:
        from backend.jumuiya.community import services as community_services
        school_name = _school_name(school_id)
        quantity = current.get("quantity", 0)
        unit = _text(current.get("unit") or "units", 40)
        item_name = _text(current.get("item_name") or "supplies", 160)
        needed_by = _text(current.get("needed_by"), 40)
        purpose = _text(current.get("purpose"), 1000)
        title = f"{school_name} needs {item_name}"
        lines = [
            f"{school_name} has an approved school supply request.",
            f"Item needed: {quantity:g} {unit} of {item_name}.",
        ]
        if needed_by:
            lines.append(f"Needed by: {needed_by}.")
        if purpose:
            lines.append(f"Purpose: {purpose}")
        post = community_services.create_post(str(user_id), {
            "title": title,
            "body": "\n\n".join(lines),
            "hub": "community",
            "type": "request",
            "category": "school_needs",
            "visibility": "public",
            "tags": ["school-needs", item_name.lower(), "elimu"],
            "location": school_name,
        })
        post_id = _text(post.get("id") or post.get("_id"), 160) if isinstance(post, dict) else ""
        if not post_id:
            raise RuntimeError("Community returned no post identifier.")
        saved = target.find_one_and_update(
            {"school_id": school_id, "_id": current["_id"], "status": "approved", "community_post_id": ""},
            {"$set": {"community_post_id": post_id, "publication_status": "published", "publication_error": "", "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )
        return {"need": _doc(saved or target.find_one({"_id": current["_id"], "school_id": school_id}))}
    except Exception as exc:
        target.update_one(
            {"school_id": school_id, "_id": current["_id"], "status": "approved", "community_post_id": ""},
            {"$set": {"publication_status": "retry_required", "publication_error": _text(str(exc), 500), "updated_at": _now()}},
        )
        latest = target.find_one({"school_id": school_id, "_id": current["_id"]})
        return {"need": _doc(latest), "warning": "Approved, but Community publication failed. Use Publish retry after checking Community availability."}
