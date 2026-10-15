# backend/jumuiya/biashara/services.py

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action

from backend.jumuiya.biashara.website import (
    DEFAULT_BIASHARA_WEBSITE_SETTINGS,
    normalize_biashara_website_settings,
)

from backend.jumuiya.biashara.models import (
    business_document,
    product_document,
    customer_document,
    order_document,
    expense_document,
    sale_document,
    inventory_movement_document,
)
from backend.jumuiya.biashara.sync.outbox import (
    build_outbox_manifest,
    dispatch_manifest_for_record,
)


logger = logging.getLogger("jumuiya.biashara.services")


# =========================================================
# HELPERS
# =========================================================

def _build_outbox_manifest(
    event_key,
    event_type,
    entity_type,
    entity_id,
    payload,
    actor_user_id,
    occurred_at=None,
):
    return build_outbox_manifest(
        event_key=event_key,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
        actor_user_id=actor_user_id,
        occurred_at=occurred_at,
    )


def _dispatch_outbox_source(source_collection_name, business_id, record_id):
    """Best-effort dispatch; the embedded manifest remains repairable on failure."""
    try:
        return dispatch_manifest_for_record(
            source_collection_name,
            str(business_id),
            record_id,
        )
    except Exception as error:
        logger.warning(
            "Biashara outbox dispatch deferred (source=%s, error=%s)",
            source_collection_name,
            type(error).__name__,
        )
        return {"enqueued": 0, "pending": 1, "errors": 1}


def now_utc():
    return datetime.now(timezone.utc)


def clean_id(value):
    """
    Convert a valid MongoDB ObjectId string to ObjectId.

    If the value is not a valid ObjectId, return it unchanged
    so the query simply won't accidentally match another object.
    """

    try:
        return ObjectId(value)

    except (InvalidId, TypeError):
        return value


def serialise(doc):
    """
    Convert MongoDB documents into JSON-safe dictionaries.
    """

    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(out.pop("_id"))

    for key, value in list(out.items()):

        if isinstance(value, ObjectId):
            out[key] = str(value)

        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()

    return out


def serialise_many(docs):
    return [
        serialise(doc)
        for doc in docs
    ]


def _bounded_list_limit(value=50):
    """Clamp list sizes even when a service is called without a route validator."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 50
    return min(max(parsed, 1), 100)


# =========================================================
# SLUGS
# =========================================================

def slugify(value):
    value = re.sub(
        r"[^a-zA-Z0-9\s-]",
        "",
        value.lower(),
    )

    value = re.sub(
        r"[\s_-]+",
        "-",
        value,
    )

    return (
        value.strip("-")
        or "business"
    )


def unique_slug(
    name,
    current_id=None,
):
    """
    Generate a unique business slug.
    """

    base = slugify(name)
    slug = base
    number = 2

    businesses = collection(
        "jumuiya_businesses"
    )

    while True:

        query = {
            "slug": slug
        }

        if current_id:
            query["_id"] = {
                "$ne": current_id
            }

        if not businesses.find_one(
            query
        ):
            return slug

        slug = f"{base}-{number}"
        number += 1


# =========================================================
# BUSINESS
# =========================================================

def get_business_for_user(user_id):
    """Resolve the caller's selected business through tenant membership."""
    from backend.jumuiya.biashara.tenancy.service import get_business_context
    try:
        return get_business_context(user_id)
    except APIError as error:
        if error.code == "business_required":
            return None
        raise


def _require_business(user_id, business_id=None):
    """Resolve an active business only after validating owner/member access."""
    from backend.jumuiya.biashara.tenancy.service import get_business_context
    return get_business_context(user_id, business_id=business_id)


def create_or_update_business(
    user_id,
    payload,
):

    businesses = collection(
        "jumuiya_businesses"
    )

    owner_id = str(user_id)
    from backend.jumuiya.biashara.tenancy.service import (
        _request_business_id,
        ensure_owner_membership,
        require_permission,
    )

    selected_business_id = _request_business_id()
    if selected_business_id:
        selected_context = require_permission(
            user_id,
            "business.manage",
            business_id=selected_business_id,
        )
        old = businesses.find_one({"_id": clean_id(selected_context["id"])})
        if not old:
            raise APIError("Business not found or access denied.", 404, "business_access_denied")
    else:
        owned_businesses = list(
            businesses.find({"owner_user_id": owner_id}).sort("created_at", 1).limit(2)
        )
        if len(owned_businesses) > 1:
            raise APIError(
                "Select which business to update by sending X-Biashara-Business-ID, or use the multi-business API to create another business.",
                409,
                "business_selection_required",
            )
        old = owned_businesses[0] if owned_businesses else None
        if old is None:
            active_memberships = list(
                collection("jumuiya_business_memberships").find({
                    "user_id": owner_id,
                    "status": "active",
                }).limit(2)
            )
            if len(active_memberships) > 1:
                raise APIError(
                    "Select a business by sending X-Biashara-Business-ID before updating a shared business profile.",
                    409,
                    "business_selection_required",
                )
            if active_memberships:
                from backend.jumuiya.biashara.tenancy.service import require_permission
                selected_context = require_permission(
                    user_id,
                    "business.manage",
                    business_id=str(active_memberships[0].get("business_id") or ""),
                )
                old = businesses.find_one({"_id": clean_id(selected_context["id"])})

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    if old:

        fields = [
            "name",
            "description",
            "phone",
            "email",
            "location",
            "county",
            "category",
            "logo_url",
        ]

        update = {
            key: payload.get(
                key,
                "",
            )
            for key in fields
        }

        update["slug"] = unique_slug(
            payload["name"],
            old["_id"],
        )

        update["updated_at"] = now_utc()

        document = businesses.find_one_and_update(
            {
                "_id": old["_id"]
            },
            {
                "$set": update
            },
            return_document=ReturnDocument.AFTER,
        )

        ensure_owner_membership(document, actor_user_id=user_id)
        log_action(
            user_id,
            "business.updated",
            "business",
            document["_id"],
        )

        from backend.jumuiya.biashara.tenancy.service import get_business_context
        return get_business_context(user_id, business_id=str(document["_id"]))

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    document = business_document(
        owner_id,
        payload,
        unique_slug(
            payload["name"]
        ),
    )

    result = businesses.insert_one(
        document
    )

    document["_id"] = result.inserted_id
    ensure_owner_membership(document, actor_user_id=user_id)

    log_action(
        user_id,
        "business.created",
        "business",
        result.inserted_id,
    )

    from backend.jumuiya.biashara.tenancy.service import get_business_context
    return get_business_context(user_id, business_id=str(document["_id"]))


# =========================================================
# PRODUCTS
# =========================================================


def create_product(user_id, payload):
    business = _require_business(user_id)
    document = product_document(business["id"], payload)
    document["_id"] = ObjectId()
    now = document.get("created_at") or now_utc()
    try:
        price_minor = int(
            Decimal(str(document.get("price", 0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100
        )
    except (InvalidOperation, TypeError, ValueError):
        raise APIError("Product price is invalid.", 422, "invalid_product_price")
    stock = Decimal(str(document.get("stock_quantity", 0) or 0))
    reserved = Decimal(str(document.get("reserved_quantity", 0) or 0))
    event = _build_outbox_manifest(
        event_key=f"product:{document['_id']}:created",
        event_type="product.created",
        entity_type="product",
        entity_id=document["_id"],
        payload={
            "status": document.get("status", "active"),
            "currency": str(document.get("currency") or business.get("currency") or "KES").upper(),
            "price_minor": price_minor,
            "stock_quantity": float(stock),
            "reserved_quantity": float(reserved),
            "available_quantity": float(stock - reserved),
            "sku": str(document.get("sku") or "")[:200],
        },
        actor_user_id=user_id,
        occurred_at=now,
    )
    document["outbox_event_manifest"] = [event]
    document["outbox_enqueued_event_keys"] = []

    collection("jumuiya_products").insert_one(document)
    _dispatch_outbox_source("jumuiya_products", business["id"], document["_id"])

    # Initial stock is an auditable movement rather than a hidden starting
    # balance. Zero-stock products need no opening movement.
    if stock > 0:
        movement_key = f"product:{document['_id']}:opening-stock"
        movement = inventory_movement_document(
            business["id"],
            document["_id"],
            {
                "movement_type": "add",
                "quantity": float(stock),
                "reason": "opening_balance",
            },
            0.0,
            float(stock),
        )
        movement.update({
            "idempotency_key": movement_key,
            "source": "product_creation",
            "actor_user_id": str(user_id),
        })
        movement["_id"] = ObjectId()
        movement_event = _build_outbox_manifest(
            event_key=f"inventory:{movement_key}",
            event_type="inventory.movement_recorded",
            entity_type="inventory_movement",
            entity_id=movement_key,
            payload={
                "product_id": str(document["_id"]),
                "movement_type": "add",
                "quantity": float(stock),
                "reason": "opening_balance",
                "previous_quantity": 0.0,
                "new_quantity": float(stock),
            },
            actor_user_id=user_id,
            occurred_at=movement.get("created_at") or now,
        )
        movement["outbox_event_manifest"] = [movement_event]
        movement["outbox_enqueued_event_keys"] = []
        collection("jumuiya_inventory_movements").insert_one(movement)
        _dispatch_outbox_source("jumuiya_inventory_movements", business["id"], movement["_id"])

    log_action(user_id, "product.created", "product", document["_id"])
    return serialise(document)

def list_products(
    user_id,
    status=None,
    category=None,
    search=None,
    limit=50,
):
    """List this business's products with filtering and a bounded limit."""
    business = _require_business(user_id)
    query = {"business_id": business["id"]}

    if status:
        query["status"] = status
    if category:
        query["category"] = category

    search_text = str(search or "").strip()
    if search_text:
        expression = {"$regex": re.escape(search_text), "$options": "i"}
        query["$or"] = [
            {"name": expression},
            {"sku": expression},
            {"category": expression},
        ]

    documents = (
        collection("jumuiya_products")
        .find(query)
        .sort("created_at", -1)
        .limit(_bounded_list_limit(limit))
    )
    return serialise_many(documents)




def update_product(user_id, product_id, payload):
    """Update catalogue metadata and route all stock changes through the stock ledger."""
    business = _require_business(user_id)
    business_id = str(business["id"])
    products = collection("jumuiya_products")
    product_query = {"_id": clean_id(product_id), "business_id": business_id}
    current = products.find_one(product_query)
    if not current:
        raise APIError("Product not found.", 404, "product_not_found")

    allowed = {
        "name", "description", "category", "sku", "price", "cost_price",
        "currency", "low_stock_threshold", "unit", "image_url", "status",
    }
    update = {key: payload[key] for key in allowed if key in payload}
    stock_was_requested = "stock_quantity" in payload
    if not update and not stock_was_requested:
        raise APIError("No product fields were provided.", 422, "empty_update")

    desired_status = str(update.get("status", current.get("status", "active"))).lower()
    reserved = Decimal(str(current.get("reserved_quantity", 0) or 0))
    if not reserved.is_finite() or reserved < 0:
        raise APIError("Product reserved stock state is invalid.", 409, "invalid_inventory_state")
    if desired_status != "active" and reserved > 0:
        raise APIError(
            "A product with stock reserved for open orders cannot be archived or deactivated. Resolve those orders first.",
            409,
            "product_has_open_reservations",
        )

    updated = current
    if update:
        event_at = now_utc()
        try:
            price_minor = int(
                (Decimal(str(update.get("price", current.get("price", 0)))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )) * 100
            )
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Product price is invalid.", 422, "invalid_product_price")

        event_manifest = _build_outbox_manifest(
            event_key=f"product:{current['_id']}:updated:{ObjectId()}",
            event_type="product.updated",
            entity_type="product",
            entity_id=current["_id"],
            payload={
                "status": desired_status,
                "currency": str(update.get("currency") or current.get("currency") or business.get("currency") or "KES").upper(),
                "price_minor": price_minor,
                "stock_quantity": float(current.get("stock_quantity", 0) or 0),
                "reserved_quantity": float(current.get("reserved_quantity", 0) or 0),
                "available_quantity": max(
                    float(current.get("stock_quantity", 0) or 0)
                    - float(current.get("reserved_quantity", 0) or 0),
                    0,
                ),
                "sku": str(update.get("sku", current.get("sku", "")) or "")[:80],
            },
            actor_user_id=user_id,
            occurred_at=event_at,
        )
        mutation_query = dict(product_query)
        mutation_query["updated_at"] = current.get("updated_at")
        # Some older product records have no updated_at. Use existence rather
        # than null equality for those records to keep optimistic locking safe.
        if "updated_at" not in current:
            mutation_query.pop("updated_at", None)
            mutation_query["$or"] = [
                {"updated_at": {"$exists": False}},
                {"updated_at": None},
            ]
        updated = products.find_one_and_update(
            mutation_query,
            {
                "$set": {**update, "updated_at": event_at},
                "$addToSet": {"outbox_event_manifest": event_manifest},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise APIError(
                "The product changed while it was being edited. Reload and retry.",
                409,
                "product_concurrent_update",
            )
        _dispatch_outbox_source("jumuiya_products", business_id, updated["_id"])
        log_action(user_id, "product.updated", "product", updated["_id"])

    if stock_was_requested:
        stock_result = inventory_adjustment(
            user_id,
            product_id,
            {
                "movement_type": "set",
                "quantity": payload["stock_quantity"],
                "reason": "product_edit",
                "idempotency_key": payload.get("idempotency_key", ""),
            },
        )
        updated = products.find_one(product_query) or stock_result.get("product") or updated

    return serialise(updated)


def delete_product(user_id, product_id):
    """Archive a product safely while preserving all historical references."""
    business = _require_business(user_id)
    business_id = str(business["id"])
    products = collection("jumuiya_products")
    query = {"_id": clean_id(product_id), "business_id": business_id}
    current = products.find_one(query)
    if not current:
        raise APIError("Product not found.", 404, "product_not_found")

    try:
        reserved = Decimal(str(current.get("reserved_quantity", 0) or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError("Product reserved stock state is invalid.", 409, "invalid_inventory_state")
    if not reserved.is_finite() or reserved < 0:
        raise APIError("Product reserved stock state is invalid.", 409, "invalid_inventory_state")
    if reserved > 0 or any(
        str(marker.get("state", "reserved")) == "reserved"
        for marker in current.get("active_reservations", []) or []
    ):
        raise APIError(
            "This product has open order reservations. Resolve those orders before archiving it.",
            409,
            "product_has_open_reservations",
        )

    now = now_utc()
    manifest = _build_outbox_manifest(
        event_key=f"product:{current['_id']}:archived:{ObjectId()}",
        event_type="product.archived",
        entity_type="product",
        entity_id=current["_id"],
        payload={
            "status": "deleted",
            "currency": str(current.get("currency") or business.get("currency") or "KES").upper(),
            "price_minor": int(
                Decimal(str(current.get("price", 0))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ) * 100
            ),
            "stock_quantity": float(current.get("stock_quantity", 0) or 0),
            "reserved_quantity": float(reserved),
            "available_quantity": max(
                float(current.get("stock_quantity", 0) or 0) - float(reserved),
                0,
            ),
            "sku": str(current.get("sku") or "")[:80],
        },
        actor_user_id=user_id,
        occurred_at=now,
    )
    document = products.find_one_and_update(
        {
            **query,
            "updated_at": current.get("updated_at"),
        } if "updated_at" in current else {
            **query,
            "$or": [{"updated_at": {"$exists": False}}, {"updated_at": None}],
        },
        {
            "$set": {
                "status": "deleted",
                "updated_at": now,
            },
            "$addToSet": {"outbox_event_manifest": manifest},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        raise APIError(
            "The product changed while it was being archived. Reload and retry.",
            409,
            "product_concurrent_update",
        )

    _dispatch_outbox_source("jumuiya_products", business_id, document["_id"])
    log_action(user_id, "product.deleted", "product", document["_id"])
    return serialise(document)


# =========================================================
# INVENTORY
# =========================================================

def low_stock(
    user_id,
    threshold=5,
):

    business = _require_business(
        user_id
    )

    try:
        threshold = float(
            threshold
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "threshold must be a number.",
            422,
            "invalid_threshold",
        )

    if threshold < 0:

        raise APIError(
            "threshold cannot be negative.",
            422,
            "invalid_threshold",
        )

    documents = collection(
        "jumuiya_products"
    ).find({
        "business_id": business["id"],
        "status": "active",
        "$expr": {
            "$lte": [
                {
                    "$subtract": [
                        {"$ifNull": ["$stock_quantity", 0]},
                        {"$ifNull": ["$reserved_quantity", 0]},
                    ]
                },
                threshold,
            ]
        },
    }).sort(
        "stock_quantity",
        1,
    )

    rows = list(documents)
    for row in rows:
        try:
            row["available_quantity"] = max(
                float(row.get("stock_quantity", 0) or 0)
                - float(row.get("reserved_quantity", 0) or 0),
                0,
            )
        except (TypeError, ValueError):
            row["available_quantity"] = 0
    return serialise_many(rows)




def _inventory_adjustment_fingerprint(product_id, movement_type, quantity, reason):
    canonical = {
        "product_id": str(product_id),
        "movement_type": str(movement_type),
        "quantity": format(Decimal(str(quantity)).normalize(), "f"),
        "reason": str(reason or "manual_adjustment").strip(),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _persist_inventory_adjustment_movement(business_id, user_id, product, marker):
    """Finish the movement side of a committed CAS mutation and clear its marker."""
    movements = collection("jumuiya_inventory_movements")
    products = collection("jumuiya_products")
    key = str(marker["idempotency_key"])
    query = {"business_id": str(business_id), "idempotency_key": key}
    movement = movements.find_one(query)
    if movement:
        if movement.get("request_fingerprint") != marker.get("request_fingerprint"):
            raise APIError("Stock idempotency key was reused with different data.", 409, "idempotency_key_reused")
    else:
        movement = inventory_movement_document(
            str(business_id),
            product["_id"],
            {
                "movement_type": marker["movement_type"],
                "quantity": marker["quantity"],
                "reason": marker["reason"],
            },
            marker["previous_available_quantity"],
            marker["new_available_quantity"],
        )
        movement.update({
            "idempotency_key": key,
            "request_fingerprint": marker["request_fingerprint"],
            "source": marker.get("source", "manual_adjustment"),
            "actor_user_id": str(marker.get("actor_user_id") or user_id),
            "previous_stock_quantity": marker["previous_stock_quantity"],
            "new_stock_quantity": marker["new_stock_quantity"],
        })
        movement["_id"] = ObjectId()
        occurred_at = marker.get("applied_at") or now_utc()
        manifest = _build_outbox_manifest(
            event_key=f"inventory:{key}",
            event_type="inventory.movement_recorded",
            entity_type="inventory_movement",
            entity_id=key,
            payload={
                "product_id": str(product["_id"]),
                "movement_type": marker["movement_type"],
                "quantity": marker["quantity"],
                "reason": marker["reason"],
                "previous_quantity": marker["previous_available_quantity"],
                "new_quantity": marker["new_available_quantity"],
                "stock_quantity": marker["new_stock_quantity"],
                "reserved_quantity": marker["new_reserved_quantity"],
                "available_quantity": marker["new_available_quantity"],
            },
            actor_user_id=marker.get("actor_user_id") or user_id,
            occurred_at=occurred_at,
        )
        movement["outbox_event_manifest"] = [manifest]
        movement["outbox_enqueued_event_keys"] = []
        try:
            movements.insert_one(movement)
        except DuplicateKeyError:
            existing = movements.find_one(query)
            if not existing or existing.get("request_fingerprint") != marker.get("request_fingerprint"):
                raise APIError("Stock mutation conflicts with an existing movement.", 409, "inventory_mutation_conflict")
            movement = existing

    products.update_one(
        {"_id": product["_id"], "business_id": str(business_id)},
        {"$pull": {"pending_inventory_mutations": {"idempotency_key": key}}},
    )
    _dispatch_outbox_source("jumuiya_inventory_movements", business_id, movement["_id"])
    _dispatch_outbox_source("jumuiya_products", business_id, product["_id"])
    latest_product = products.find_one({"_id": product["_id"], "business_id": str(business_id)}) or product
    return latest_product, movement


def inventory_adjustment(user_id, product_id, payload):
    """Adjust inventory using compare-and-set, durable recovery markers and idempotent movements."""
    business = _require_business(user_id)
    business_id = str(business["id"])
    products = collection("jumuiya_products")
    movements = collection("jumuiya_inventory_movements")
    product_query = {"_id": clean_id(product_id), "business_id": business_id}

    movement_type = str(payload.get("movement_type") or "").strip().lower()
    if movement_type not in {"add", "remove", "set"}:
        raise APIError("Invalid inventory movement.", 422, "invalid_movement")
    try:
        quantity = Decimal(str(payload["quantity"]))
    except (InvalidOperation, TypeError, ValueError, KeyError):
        raise APIError("Stock quantities must be valid numbers.", 422, "invalid_stock_quantity")
    if not quantity.is_finite() or quantity < 0 or (movement_type != "set" and quantity <= 0):
        raise APIError("Stock adjustment quantity is invalid.", 422, "invalid_stock_quantity")

    reason = str(payload.get("reason") or "manual_adjustment").strip()[:300]
    client_key = str(payload.get("idempotency_key") or "").strip()
    if client_key and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", client_key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")
    # Give every persisted mutation a unique movement key. Clients should
    # provide Idempotency-Key to make network retries refer to the same action.
    mutation_key = client_key or ("stock-adjust:" + str(ObjectId()))
    fingerprint = _inventory_adjustment_fingerprint(product_id, movement_type, quantity, reason)

    product = products.find_one(product_query)
    if not product:
        raise APIError("Product not found.", 404, "product_not_found")

    existing_movement = movements.find_one({
        "business_id": business_id,
        "idempotency_key": mutation_key,
    })
    if existing_movement:
        if existing_movement.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused with different stock adjustment data.", 409, "idempotency_key_reused")
        products.update_one(
            product_query,
            {"$pull": {"pending_inventory_mutations": {"idempotency_key": mutation_key}}},
        )
        _dispatch_outbox_source("jumuiya_inventory_movements", business_id, existing_movement["_id"])
        return {
            "product": serialise(products.find_one(product_query) or product),
            "movement": serialise(existing_movement),
            "replayed": True,
        }

    pending_marker = next(
        (
            marker for marker in (product.get("pending_inventory_mutations") or [])
            if str(marker.get("idempotency_key")) == mutation_key
        ),
        None,
    )
    if pending_marker:
        if pending_marker.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused with different stock adjustment data.", 409, "idempotency_key_reused")
        repaired_product, repaired_movement = _persist_inventory_adjustment_movement(
            business_id, user_id, product, pending_marker
        )
        return {
            "product": serialise(repaired_product),
            "movement": serialise(repaired_movement),
            "replayed": True,
        }

    try:
        previous_stock = Decimal(str(product.get("stock_quantity", 0) or 0))
        reserved_stock = Decimal(str(product.get("reserved_quantity", 0) or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
    if (
        not previous_stock.is_finite()
        or not reserved_stock.is_finite()
        or previous_stock < 0
        or reserved_stock < 0
        or reserved_stock > previous_stock
    ):
        raise APIError("Product inventory state is inconsistent.", 409, "invalid_inventory_state")

    if movement_type == "add":
        new_stock = previous_stock + quantity
    elif movement_type == "remove":
        available_stock = previous_stock - reserved_stock
        if quantity > available_stock:
            raise APIError(
                "Insufficient available stock. Some units are reserved for open orders.",
                409,
                "insufficient_stock",
            )
        new_stock = previous_stock - quantity
    else:
        if quantity < reserved_stock:
            raise APIError(
                "Stock cannot be set below the quantity reserved by open orders.",
                409,
                "stock_below_reserved",
            )
        new_stock = quantity

    if new_stock == previous_stock:
        return {
            "product": serialise(product),
            "movement": None,
            "replayed": True,
        }

    now = now_utc()
    marker = {
        "idempotency_key": mutation_key,
        "request_fingerprint": fingerprint,
        "movement_type": movement_type,
        "quantity": float(quantity),
        "reason": reason,
        "source": "manual_adjustment",
        "actor_user_id": str(user_id),
        "previous_stock_quantity": float(previous_stock),
        "new_stock_quantity": float(new_stock),
        "previous_reserved_quantity": float(reserved_stock),
        "new_reserved_quantity": float(reserved_stock),
        "previous_available_quantity": float(previous_stock - reserved_stock),
        "new_available_quantity": float(new_stock - reserved_stock),
        "applied_at": now,
    }
    product_event = _build_outbox_manifest(
        event_key=f"product:{product['_id']}:inventory:{mutation_key}",
        event_type="product.inventory_adjusted",
        entity_type="product",
        entity_id=product["_id"],
        payload={
            "product_id": str(product["_id"]),
            "movement_type": movement_type,
            "quantity": float(quantity),
            "reason": reason,
            "stock_quantity": float(new_stock),
            "reserved_quantity": float(reserved_stock),
            "available_quantity": float(new_stock - reserved_stock),
            "currency": str(product.get("currency") or business.get("currency") or "KES").upper(),
        },
        actor_user_id=user_id,
        occurred_at=now,
    )
    filter_doc = {
        **product_query,
        "stock_quantity": product.get("stock_quantity", 0),
        "pending_inventory_mutations.idempotency_key": {"$ne": mutation_key},
    }
    if "reserved_quantity" in product:
        filter_doc["reserved_quantity"] = product["reserved_quantity"]
    else:
        filter_doc["reserved_quantity"] = {"$exists": False}

    updated = products.find_one_and_update(
        filter_doc,
        {
            "$set": {"stock_quantity": float(new_stock), "updated_at": now},
            "$addToSet": {
                "pending_inventory_mutations": marker,
                "outbox_event_manifest": product_event,
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        # A duplicate idempotency-key call may have committed between our read
        # and compare-and-set. Return that result only if its fingerprint matches.
        existing_movement = movements.find_one({
            "business_id": business_id,
            "idempotency_key": mutation_key,
        })
        if existing_movement and existing_movement.get("request_fingerprint") == fingerprint:
            _dispatch_outbox_source("jumuiya_inventory_movements", business_id, existing_movement["_id"])
            return {
                "product": serialise(products.find_one(product_query) or product),
                "movement": serialise(existing_movement),
                "replayed": True,
            }
        raise APIError(
            "Inventory changed while this adjustment was being saved. Reload and retry.",
            409,
            "inventory_concurrent_update",
        )

    repaired_product, movement = _persist_inventory_adjustment_movement(
        business_id, user_id, updated, marker
    )
    log_action(user_id, "inventory.adjusted", "product", product["_id"], {
        "movement_type": movement_type,
        "quantity": float(quantity),
        "idempotency_key": mutation_key,
    })
    return {
        "product": serialise(repaired_product),
        "movement": serialise(movement),
        "replayed": False,
    }


def repair_pending_inventory_movements(user_id, limit=100):
    """Recover stock mutations whose product write committed before movement insert."""
    business = _require_business(user_id)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100
    limit = min(max(limit, 1), 100)
    products = collection("jumuiya_products")
    query = {
        "business_id": str(business["id"]),
        "pending_inventory_mutations.0": {"$exists": True},
    }
    report = {"products_scanned": 0, "movements_repaired": 0, "errors": 0}
    for product in products.find(query).limit(limit):
        report["products_scanned"] += 1
        for marker in product.get("pending_inventory_mutations") or []:
            try:
                existing = collection("jumuiya_inventory_movements").find_one({
                    "business_id": str(business["id"]),
                    "idempotency_key": marker.get("idempotency_key"),
                })
                if existing:
                    if existing.get("request_fingerprint") != marker.get("request_fingerprint"):
                        raise APIError("Pending inventory marker conflicts with a movement.", 409, "inventory_mutation_conflict")
                    products.update_one(
                        {"_id": product["_id"], "business_id": str(business["id"])},
                        {"$pull": {"pending_inventory_mutations": {"idempotency_key": marker.get("idempotency_key")}}},
                    )
                    _dispatch_outbox_source("jumuiya_inventory_movements", business["id"], existing["_id"])
                else:
                    _persist_inventory_adjustment_movement(business["id"], user_id, product, marker)
                    report["movements_repaired"] += 1
            except Exception as error:
                report["errors"] += 1
                logger.warning(
                    "Biashara inventory movement repair deferred (error=%s)",
                    type(error).__name__,
                )
    return report

def _order_fingerprint(payload):
    """Stable fingerprint of order intent, excluding client prices and totals."""
    items = []
    for item in payload.get("items", []):
        try:
            quantity = Decimal(str(item.get("quantity", 0)))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Order quantity is invalid.", 422, "invalid_order_quantity")
        if not quantity.is_finite() or quantity <= 0:
            raise APIError("Order quantities must be positive finite numbers.", 422, "invalid_order_quantity")
        items.append({
            "product_id": str(item.get("product_id") or ""),
            "quantity": format(quantity.normalize(), "f"),
        })
    canonical = {
        "customer_id": str(payload.get("customer_id") or ""),
        "items": items,
        "notes": str(payload.get("notes") or "").strip(),
        "source_channel": str(payload.get("source_channel") or "manual").strip().lower(),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _order_quantities(order):
    """Aggregate repeated SKU/product lines so reservation happens once per product."""
    quantities = {}
    for item in order.get("items", []):
        product_id = str(item.get("product_id") or "")
        try:
            quantity = Decimal(str(item.get("quantity")))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Stored order quantity is invalid.", 409, "invalid_order_inventory")
        if not product_id or not quantity.is_finite() or quantity <= 0:
            raise APIError("Stored order item is invalid.", 409, "invalid_order_inventory")
        quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
    return quantities


def _reservation_for(product, order_id):
    """Find one product's reservation marker for an order, independent of BSON IDs."""
    for reservation in product.get("active_reservations", []) or []:
        if str(reservation.get("order_id")) == str(order_id):
            return reservation
    return None


def _inventory_movement_key(order_id, product_id, operation):
    return f"biashara:order:{order_id}:{operation}:{product_id}"


def _ensure_order_movement(
    business_id,
    user_id,
    order_id,
    product_id,
    operation,
    movement_type,
    reason,
    quantity,
    previous_quantity,
    new_quantity,
):
    """Persist a uniquely-keyed inventory fact; safe to call during recovery."""
    movements = collection("jumuiya_inventory_movements")
    key = _inventory_movement_key(order_id, product_id, operation)
    existing = movements.find_one({
        "business_id": str(business_id),
        "idempotency_key": key,
    })
    if existing:
        _dispatch_outbox_source("jumuiya_inventory_movements", business_id, existing["_id"])
        return existing

    document = inventory_movement_document(
        str(business_id),
        clean_id(product_id),
        {
            "movement_type": movement_type,
            "quantity": float(quantity),
            "reason": reason,
        },
        float(previous_quantity),
        float(new_quantity),
    )
    document.update({
        "idempotency_key": key,
        "order_id": str(order_id),
        "actor_user_id": str(user_id),
        "source": "order_lifecycle",
    })
    document["_id"] = ObjectId()
    occurred_at = document.get("created_at") or now_utc()
    movement_event = _build_outbox_manifest(
        event_key=f"inventory:{key}",
        event_type="inventory.movement_recorded",
        entity_type="inventory_movement",
        entity_id=key,
        payload={
            "order_id": str(order_id),
            "product_id": str(product_id),
            "movement_type": movement_type,
            "quantity": float(quantity),
            "reason": str(reason),
            "previous_quantity": float(previous_quantity),
            "new_quantity": float(new_quantity),
        },
        actor_user_id=user_id,
        occurred_at=occurred_at,
    )
    document["outbox_event_manifest"] = [movement_event]
    document["outbox_enqueued_event_keys"] = []
    try:
        movements.insert_one(document)
        _dispatch_outbox_source("jumuiya_inventory_movements", business_id, document["_id"])
        return document
    except DuplicateKeyError:
        existing = movements.find_one({
            "business_id": str(business_id),
            "idempotency_key": key,
        })
        if existing:
            _dispatch_outbox_source("jumuiya_inventory_movements", business_id, existing["_id"])
            return existing
        raise


def _ensure_reservation_movement(business_id, user_id, order_id, product_id, reservation):
    return _ensure_order_movement(
        business_id=business_id,
        user_id=user_id,
        order_id=order_id,
        product_id=product_id,
        operation="reserve",
        movement_type="remove",
        reason="order_reservation",
        quantity=reservation["quantity"],
        previous_quantity=reservation["previous_available_quantity"],
        new_quantity=reservation["new_available_quantity"],
    )


def _release_order_inventory(order, user_id, allow_missing=False):
    """Release open-order reservations exactly once and recover interrupted releases."""
    business_id = str(order["business_id"])
    order_id = str(order.get("_id") or order.get("id"))
    products = collection("jumuiya_products")
    movements = collection("jumuiya_inventory_movements")

    for product_id, quantity in _order_quantities(order).items():
        release_key = _inventory_movement_key(order_id, product_id, "release")
        consume_key = _inventory_movement_key(order_id, product_id, "consume")
        while True:
            product = products.find_one({
                "_id": clean_id(product_id),
                "business_id": business_id,
            })
            if not product:
                if movements.find_one({"business_id": business_id, "idempotency_key": release_key}):
                    break
                if allow_missing:
                    break
                raise APIError(
                    "A reserved product is missing; inventory needs reconciliation.",
                    409,
                    "inventory_reservation_missing",
                )

            reservation = _reservation_for(product, order_id)
            if reservation is None:
                if movements.find_one({"business_id": business_id, "idempotency_key": release_key}):
                    break
                if movements.find_one({"business_id": business_id, "idempotency_key": consume_key}):
                    raise APIError(
                        "Stock has already been consumed by this order and cannot be released as a cancellation.",
                        409,
                        "order_inventory_consumed",
                    )
                if allow_missing or order.get("inventory_status") in {None, "", "not_reserved", "reservation_failed", "reservation_pending"}:
                    break
                raise APIError(
                    "The order reservation marker is missing; inventory needs reconciliation.",
                    409,
                    "inventory_reservation_missing",
                )

            state = reservation.get("state", "reserved")
            if state == "consumed":
                raise APIError(
                    "Stock has already been consumed by this order and cannot be released as a cancellation.",
                    409,
                    "order_inventory_consumed",
                )

            if state == "released":
                _ensure_order_movement(
                    business_id, user_id, order_id, product_id, "release", "add",
                    "order_cancelled", reservation["quantity"],
                    reservation["release_previous_available_quantity"],
                    reservation["release_new_available_quantity"],
                )
                products.update_one(
                    {"_id": product["_id"], "business_id": business_id},
                    {"$pull": {"active_reservations": {"order_id": order_id}}},
                )
                break

            try:
                stock = Decimal(str(product.get("stock_quantity", 0) or 0))
                reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
            if not stock.is_finite() or not reserved.is_finite() or reserved < quantity:
                raise APIError("Reserved inventory is inconsistent and needs reconciliation.", 409, "invalid_inventory_state")

            previous_available = stock - reserved
            new_reserved = reserved - quantity
            new_available = stock - new_reserved
            now = now_utc()
            updated = products.find_one_and_update(
                {
                    "_id": product["_id"],
                    "business_id": business_id,
                    "stock_quantity": product.get("stock_quantity", 0),
                    "reserved_quantity": product.get("reserved_quantity", 0),
                    "active_reservations": {
                        "$elemMatch": {"order_id": order_id, "state": "reserved"}
                    },
                },
                {
                    "$inc": {"reserved_quantity": -float(quantity)},
                    "$set": {
                        "updated_at": now,
                        "active_reservations.$[reservation].state": "released",
                        "active_reservations.$[reservation].release_previous_available_quantity": float(previous_available),
                        "active_reservations.$[reservation].release_new_available_quantity": float(new_available),
                        "active_reservations.$[reservation].released_at": now,
                    },
                },
                array_filters=[{"reservation.order_id": order_id, "reservation.state": "reserved"}],
                return_document=ReturnDocument.AFTER,
            )
            if not updated:
                continue

            updated_reservation = _reservation_for(updated, order_id)
            if not updated_reservation:
                raise APIError("Reservation release needs reconciliation.", 409, "inventory_reservation_missing")
            _ensure_order_movement(
                business_id, user_id, order_id, product_id, "release", "add",
                "order_cancelled", quantity,
                updated_reservation["release_previous_available_quantity"],
                updated_reservation["release_new_available_quantity"],
            )
            products.update_one(
                {"_id": product["_id"], "business_id": business_id},
                {"$pull": {"active_reservations": {"order_id": order_id}}},
            )
            break

    collection("jumuiya_orders").update_one(
        {"_id": clean_id(order_id), "business_id": business_id},
        {"$set": {"inventory_status": "released", "inventory_released_at": now_utc()}},
    )


def _reserve_order_inventory(order, user_id):
    """Reserve available stock with compare-and-set writes and crash-recoverable markers."""
    business_id = str(order["business_id"])
    order_id = str(order.get("_id") or order.get("id"))
    products = collection("jumuiya_products")
    quantities = _order_quantities(order)

    for product_id, quantity in quantities.items():
        reserved_done = False
        for _attempt in range(12):
            product = products.find_one({
                "_id": clean_id(product_id),
                "business_id": business_id,
            })
            if not product:
                raise APIError("One or more products are no longer available.", 422, "invalid_product")

            reservation = _reservation_for(product, order_id)
            if reservation:
                state = reservation.get("state", "reserved")
                if state == "reserved":
                    _ensure_reservation_movement(business_id, user_id, order_id, product_id, reservation)
                    reserved_done = True
                    break
                if state == "consumed":
                    # A duplicate request after fulfilment must not reserve again.
                    reserved_done = True
                    break
                if state == "released":
                    raise APIError("This order's inventory reservation was already released.", 409, "order_inventory_released")

            if product.get("status", "active") != "active":
                raise APIError("One or more products are no longer available.", 422, "invalid_product")

            try:
                stock = Decimal(str(product.get("stock_quantity", 0) or 0))
                reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
            if not stock.is_finite() or not reserved.is_finite() or stock < 0 or reserved < 0 or reserved > stock:
                raise APIError("Product inventory state is inconsistent.", 409, "invalid_inventory_state")

            available = stock - reserved
            if available < quantity:
                raise APIError(
                    f"Insufficient available stock for {product.get('name', 'product')}.",
                    409,
                    "insufficient_stock",
                )

            new_reserved = reserved + quantity
            now = now_utc()
            marker = {
                "order_id": order_id,
                "quantity": float(quantity),
                "state": "reserved",
                "previous_available_quantity": float(available),
                "new_available_quantity": float(stock - new_reserved),
                "previous_reserved_quantity": float(reserved),
                "new_reserved_quantity": float(new_reserved),
                "reserved_at": now,
            }
            filter_doc = {
                "_id": product["_id"],
                "business_id": business_id,
                "status": "active",
                "stock_quantity": product.get("stock_quantity", 0),
                "active_reservations.order_id": {"$ne": order_id},
            }
            if "reserved_quantity" in product:
                filter_doc["reserved_quantity"] = product["reserved_quantity"]
            else:
                filter_doc["reserved_quantity"] = {"$exists": False}

            updated = products.find_one_and_update(
                filter_doc,
                {
                    "$inc": {"reserved_quantity": float(quantity)},
                    "$set": {"updated_at": now},
                    "$addToSet": {"active_reservations": marker},
                },
                return_document=ReturnDocument.AFTER,
            )
            if updated:
                saved_marker = _reservation_for(updated, order_id)
                if not saved_marker:
                    raise APIError("Inventory reservation needs reconciliation.", 409, "inventory_reservation_missing")
                _ensure_reservation_movement(business_id, user_id, order_id, product_id, saved_marker)
                reserved_done = True
                break

        if not reserved_done:
            # Re-check after bounded compare-and-set retries; never overbook stock.
            raise APIError(
                "Inventory changed while reserving this order. Retry with the same idempotency key.",
                409,
                "inventory_reservation_conflict",
            )

    current = collection("jumuiya_orders").find_one({
        "_id": clean_id(order_id),
        "business_id": business_id,
    })
    if not current:
        raise APIError("Order record disappeared during reservation.", 409, "order_reservation_missing")
    if current.get("status") not in {"pending", "confirmed"}:
        _release_order_inventory(current, user_id, allow_missing=True)
        raise APIError("The order changed while inventory was being reserved.", 409, "order_state_conflict")

    order_collection = collection("jumuiya_orders")
    current_order = order_collection.find_one({
        "_id": clean_id(order_id),
        "business_id": business_id,
    })
    reserved_at = now_utc()
    reserve_event = _build_outbox_manifest(
        event_key=f"order:{order_id}:inventory:reserved",
        event_type="order.inventory_reserved",
        entity_type="order",
        entity_id=order_id,
        payload={
            "status": (current_order or order).get("status", "pending"),
            "inventory_status": "reserved",
            "source_channel": (current_order or order).get("source_channel", "manual"),
            "total_amount_minor": (current_order or order).get("total_amount_minor"),
            "currency": (current_order or order).get("currency", "KES"),
        },
        actor_user_id=user_id,
        occurred_at=reserved_at,
    )
    order_collection.update_one(
        {
            "_id": clean_id(order_id),
            "business_id": business_id,
            "status": {"$in": ["pending", "confirmed"]},
        },
        {
            "$set": {"inventory_status": "reserved", "reserved_at": reserved_at},
            "$addToSet": {"outbox_event_manifest": reserve_event},
        },
    )
    _dispatch_outbox_source("jumuiya_orders", business_id, clean_id(order_id))


def _fail_order_reservation(order, user_id, error):
    order_id = str(order.get("_id") or order.get("id"))
    business_id = str(order["business_id"])
    try:
        _release_order_inventory(order, user_id, allow_missing=True)
        collection("jumuiya_orders").update_one(
            {"_id": clean_id(order_id), "business_id": business_id, "status": "pending"},
            {
                "$set": {
                    "status": "cancelled",
                    "inventory_status": "reservation_failed",
                    "cancellation_reason": "inventory_reservation_failed",
                    "cancelled_at": now_utc(),
                    "updated_at": now_utc(),
                },
                "$push": {
                    "status_history": {
                        "from": "pending",
                        "to": "cancelled",
                        "at": now_utc().isoformat(),
                        "actor_user_id": str(user_id),
                        "reason": "inventory_reservation_failed",
                    }
                },
            },
        )
    except Exception:
        # Preserve the failed reservation record for operator recovery; never
        # silently claim the stock was released if compensation did not finish.
        collection("jumuiya_orders").update_one(
            {"_id": clean_id(order_id), "business_id": business_id},
            {"$set": {
                "inventory_status": "release_reconciliation_required",
                "inventory_reconciliation_required_at": now_utc(),
            }},
        )
        log_action(
            user_id,
            "inventory.reservation_reconciliation_required",
            "order",
            order_id,
            {"error_code": getattr(error, "code", "reservation_failed")},
        )


def create_order(user_id, payload):
    """Create an order with catalogue-authoritative pricing and recoverable stock reservation."""
    business = _require_business(user_id)
    customer_id = payload.get("customer_id")
    if customer_id:
        customer = collection("jumuiya_customers").find_one({
            "_id": clean_id(customer_id),
            "business_id": business["id"],
        })
        if not customer:
            raise APIError("Customer does not belong to this business.", 422, "invalid_customer")

    submitted_items = payload.get("items")
    if not isinstance(submitted_items, list) or not submitted_items:
        raise APIError("An order must contain at least one item.", 422, "invalid_order_items")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", idempotency_key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")

    fingerprint = _order_fingerprint(payload)
    orders = collection("jumuiya_orders")
    if idempotency_key:
        existing = orders.find_one({
            "business_id": str(business["id"]),
            "idempotency_key": idempotency_key,
        })
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError(
                    "This Idempotency-Key was already used for a different order payload.",
                    409,
                    "idempotency_key_reused",
                )
            if existing.get("inventory_status") == "reservation_pending" and existing.get("status") in {"pending", "confirmed"}:
                try:
                    _reserve_order_inventory(existing, user_id)
                except APIError as error:
                    _fail_order_reservation(existing, user_id, error)
                    raise
                existing = orders.find_one({"_id": existing["_id"], "business_id": str(business["id"])}) or existing
            if existing.get("inventory_status") in {"reservation_failed", "release_reconciliation_required"}:
                raise APIError(
                    "This order's stock reservation did not complete. Review the order before creating another request.",
                    409,
                    "order_reservation_failed",
                )
            _dispatch_outbox_source("jumuiya_orders", business["id"], existing["_id"])
            return serialise(existing)

    currency = str(business.get("currency") or "KES").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "KES"

    product_cache = {}
    quantities = {}
    priced_items = []
    subtotal = Decimal("0.00")
    for index, item in enumerate(submitted_items):
        if not isinstance(item, dict):
            raise APIError(f"Order item {index + 1} must be an object.", 422, "invalid_order_items")
        product_id = str(item.get("product_id") or "")
        if not product_id:
            raise APIError(f"Order item {index + 1} requires a product.", 422, "invalid_order_items")
        product = product_cache.get(product_id)
        if product is None:
            product = collection("jumuiya_products").find_one({
                "_id": clean_id(product_id),
                "business_id": str(business["id"]),
                "status": "active",
            })
            if not product:
                raise APIError("One or more products are no longer available.", 422, "invalid_product")
            product_cache[product_id] = product

        try:
            quantity = Decimal(str(item.get("quantity")))
            unit_price = Decimal(str(product.get("price", 0)))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Order quantity or catalogue price is invalid.", 422, "invalid_order_amount")
        if not quantity.is_finite() or quantity <= 0:
            raise APIError("Order quantities must be positive finite numbers.", 422, "invalid_order_quantity")
        if not unit_price.is_finite() or unit_price < 0:
            raise APIError(f"Catalogue price for {product.get('name', 'product')} is invalid.", 409, "invalid_catalogue_price")
        if str(product.get("currency") or currency).upper() != currency:
            raise APIError("All products in one order must use the business currency.", 422, "mixed_order_currency")

        rounded_price = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_total = (rounded_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += line_total
        quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
        priced_items.append({
            "product_id": str(product.get("_id")),
            "name": str(product.get("name") or "Product")[:160],
            "sku": str(product.get("sku") or "")[:80],
            "quantity": float(quantity),
            "unit_price": float(rounded_price),
            "unit_price_minor": int(rounded_price * 100),
            "line_total": float(line_total),
            "line_total_minor": int(line_total * 100),
            "currency": currency,
        })

    subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    now = now_utc()
    trusted_payload = {
        "customer_id": str(customer_id) if customer_id else None,
        "items": priced_items,
        "subtotal": float(subtotal),
        "discount": 0,
        "total_amount": float(subtotal),
        "currency": currency,
        "notes": str(payload.get("notes") or "")[:1000],
        "status": "pending",
        "payment_status": "unpaid",
    }
    document = order_document(str(business["id"]), trusted_payload)
    document.update({
        "_id": ObjectId(),
        "subtotal_minor": int(subtotal * 100),
        "total_amount_minor": int(subtotal * 100),
        "currency": currency,
        "source_channel": str(payload.get("source_channel") or "manual"),
        "inventory_status": "reservation_pending",
        "inventory_reserved_quantity": {key: float(value) for key, value in quantities.items()},
        "request_fingerprint": fingerprint,
        "status_history": [{
            "from": None,
            "to": "pending",
            "at": now.isoformat(),
            "actor_user_id": str(user_id),
        }],
    })
    created_event = _build_outbox_manifest(
        event_key=f"order:{document['_id']}:created",
        event_type="order.created",
        entity_type="order",
        entity_id=document["_id"],
        payload={
            "status": "pending",
            "inventory_status": "reservation_pending",
            "source_channel": document["source_channel"],
            "total_amount_minor": int(subtotal * 100),
            "currency": currency,
        },
        actor_user_id=user_id,
        occurred_at=now,
    )
    document["outbox_event_manifest"] = [created_event]
    document["outbox_enqueued_event_keys"] = []
    if idempotency_key:
        document["idempotency_key"] = idempotency_key

    try:
        orders.insert_one(document)
    except DuplicateKeyError:
        if idempotency_key:
            existing = orders.find_one({
                "business_id": str(business["id"]),
                "idempotency_key": idempotency_key,
            })
            if existing and existing.get("request_fingerprint") == fingerprint:
                return create_order(user_id, {**payload, "idempotency_key": idempotency_key})
            if existing:
                raise APIError("Idempotency-Key was reused for a different order.", 409, "idempotency_key_reused")
        raise

    log_action(user_id, "order.created", "order", document["_id"], {"source_channel": document["source_channel"]})
    try:
        _reserve_order_inventory(document, user_id)
    except APIError as error:
        _fail_order_reservation(document, user_id, error)
        raise

    saved = orders.find_one({"_id": document["_id"], "business_id": str(business["id"])}) or document
    _dispatch_outbox_source("jumuiya_orders", business["id"], document["_id"])
    log_action(user_id, "inventory.order_reserved", "order", document["_id"])
    return serialise(saved)

def list_orders(
    user_id,
    status=None,
    limit=50,
):
    """List this business's orders with optional status and bounded limit."""
    business = _require_business(user_id)
    query = {"business_id": business["id"]}

    if status:
        query["status"] = status

    documents = (
        collection("jumuiya_orders")
        .find(query)
        .sort("created_at", -1)
        .limit(_bounded_list_limit(limit))
    )
    return serialise_many(documents)


def get_order(
    user_id,
    order_id,
):

    business = _require_business(
        user_id
    )

    document = collection(
        "jumuiya_orders"
    ).find_one({
        "_id": clean_id(
            order_id
        ),
        "business_id": business["id"],
    })

    if not document:

        raise APIError(
            "Order not found.",
            404,
            "order_not_found",
        )

    return serialise(
        document
    )



def _consume_order_inventory(order, user_id):
    """Convert reserved units into sold/on-hand stock exactly once."""
    business_id = str(order["business_id"])
    order_id = str(order.get("_id") or order.get("id"))
    products = collection("jumuiya_products")
    movements = collection("jumuiya_inventory_movements")
    quantities = _order_quantities(order)

    # Legacy orders created before reservations existed are reserved now before
    # processing. This prevents old records from bypassing stock validation.
    has_reservation = False
    for product_id in quantities:
        product = products.find_one({"_id": clean_id(product_id), "business_id": business_id})
        if product and _reservation_for(product, order_id):
            has_reservation = True
            break
    if not has_reservation and order.get("inventory_status") in {None, "", "not_reserved"}:
        _reserve_order_inventory(order, user_id)
        order = collection("jumuiya_orders").find_one({
            "_id": clean_id(order_id),
            "business_id": business_id,
        }) or order

    for product_id, quantity in quantities.items():
        consume_key = _inventory_movement_key(order_id, product_id, "consume")
        done = False
        for _attempt in range(12):
            product = products.find_one({
                "_id": clean_id(product_id),
                "business_id": business_id,
            })
            if not product:
                if movements.find_one({"business_id": business_id, "idempotency_key": consume_key}):
                    done = True
                    break
                raise APIError("Reserved product is missing; inventory needs reconciliation.", 409, "inventory_reservation_missing")

            reservation = _reservation_for(product, order_id)
            if reservation is None:
                if movements.find_one({"business_id": business_id, "idempotency_key": consume_key}):
                    done = True
                    break
                raise APIError("Order stock reservation is missing; inventory needs reconciliation.", 409, "inventory_reservation_missing")

            state = reservation.get("state", "reserved")
            if state == "released":
                raise APIError("Order stock reservation has already been released.", 409, "order_inventory_released")
            if state == "consumed":
                _ensure_order_movement(
                    business_id, user_id, order_id, product_id, "consume", "remove",
                    "order_fulfilled", reservation["quantity"],
                    reservation["consumption_previous_stock_quantity"],
                    reservation["consumption_new_stock_quantity"],
                )
                products.update_one(
                    {"_id": product["_id"], "business_id": business_id},
                    {"$pull": {"active_reservations": {"order_id": order_id}}},
                )
                done = True
                break

            try:
                stock = Decimal(str(product.get("stock_quantity", 0) or 0))
                reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
            if not stock.is_finite() or not reserved.is_finite() or stock < quantity or reserved < quantity:
                raise APIError("Reserved inventory is inconsistent and needs reconciliation.", 409, "invalid_inventory_state")

            new_stock = stock - quantity
            new_reserved = reserved - quantity
            now = now_utc()
            updated = products.find_one_and_update(
                {
                    "_id": product["_id"],
                    "business_id": business_id,
                    "stock_quantity": product.get("stock_quantity", 0),
                    "reserved_quantity": product.get("reserved_quantity", 0),
                    "active_reservations": {
                        "$elemMatch": {"order_id": order_id, "state": "reserved"}
                    },
                },
                {
                    "$inc": {
                        "stock_quantity": -float(quantity),
                        "reserved_quantity": -float(quantity),
                    },
                    "$set": {
                        "updated_at": now,
                        "active_reservations.$[reservation].state": "consumed",
                        "active_reservations.$[reservation].consumption_previous_stock_quantity": float(stock),
                        "active_reservations.$[reservation].consumption_new_stock_quantity": float(new_stock),
                        "active_reservations.$[reservation].consumption_previous_available_quantity": float(stock - reserved),
                        "active_reservations.$[reservation].consumption_new_available_quantity": float(new_stock - new_reserved),
                        "active_reservations.$[reservation].consumed_at": now,
                    },
                },
                array_filters=[{"reservation.order_id": order_id, "reservation.state": "reserved"}],
                return_document=ReturnDocument.AFTER,
            )
            if not updated:
                continue

            saved_reservation = _reservation_for(updated, order_id)
            if not saved_reservation:
                raise APIError("Stock consumption needs reconciliation.", 409, "inventory_reservation_missing")
            _ensure_order_movement(
                business_id, user_id, order_id, product_id, "consume", "remove",
                "order_fulfilled", quantity,
                saved_reservation["consumption_previous_stock_quantity"],
                saved_reservation["consumption_new_stock_quantity"],
            )
            products.update_one(
                {"_id": product["_id"], "business_id": business_id},
                {"$pull": {"active_reservations": {"order_id": order_id}}},
            )
            done = True
            break

        if not done:
            raise APIError(
                "Inventory changed while fulfilling this order. Retry the same status update.",
                409,
                "inventory_consumption_conflict",
            )

    collection("jumuiya_orders").update_one(
        {"_id": clean_id(order_id), "business_id": business_id, "status": "confirmed"},
        {"$set": {"inventory_status": "consumed", "inventory_consumed_at": now_utc()}},
    )


def update_order_status(user_id, order_id, status):
    """Apply legal order transitions and make stock effects recoverable."""
    transitions = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"processing", "cancelled"},
        "processing": {"completed"},
        "completed": set(),
        "cancelled": set(),
    }
    if not isinstance(status, str) or status not in transitions:
        raise APIError("Invalid order status.", 422, "invalid_order_status")

    business = _require_business(user_id)
    orders = collection("jumuiya_orders")
    document = orders.find_one({
        "_id": clean_id(order_id),
        "business_id": business["id"],
    })
    if not document:
        raise APIError("Order not found.", 404, "order_not_found")

    previous_status = str(document.get("status") or "pending").lower()
    if previous_status == status:
        _dispatch_outbox_source("jumuiya_orders", business["id"], document["_id"])
        return serialise(document)
    if status not in transitions.get(previous_status, set()):
        raise APIError(
            f"Order cannot move from {previous_status} to {status}.",
            409,
            "invalid_order_transition",
        )

    order_id_string = str(document.get("_id") or document.get("id"))
    if status == "processing":
        _consume_order_inventory(document, user_id)
    elif status == "cancelled":
        _release_order_inventory(document, user_id)

    now = now_utc()
    order_after_inventory = orders.find_one({
        "_id": document["_id"],
        "business_id": business["id"],
    }) or document
    status_event_manifest = _build_outbox_manifest(
        event_key=f"order:{order_id_string}:status:{status}",
        event_type="order.status_changed",
        entity_type="order",
        entity_id=order_id_string,
        payload={
            "previous_status": previous_status,
            "status": status,
            "inventory_status": order_after_inventory.get("inventory_status", "unknown"),
            "source_channel": order_after_inventory.get("source_channel", "manual"),
            "total_amount_minor": order_after_inventory.get("total_amount_minor"),
            "currency": order_after_inventory.get("currency", "KES"),
        },
        actor_user_id=user_id,
        occurred_at=now,
    )
    update = {"status": status, "updated_at": now}
    if status == "completed":
        update["completed_at"] = now
    elif status == "cancelled":
        update["cancelled_at"] = now

    event = {
        "from": previous_status,
        "to": status,
        "at": now.isoformat(),
        "actor_user_id": str(user_id),
    }
    updated = orders.find_one_and_update(
        {
            "_id": document["_id"],
            "business_id": business["id"],
            "status": previous_status,
        },
        {
            "$set": update,
            "$push": {"status_history": event},
            "$addToSet": {"outbox_event_manifest": status_event_manifest},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        # Inventory operations are idempotent, so a retry can complete the
        # state transition without decrementing or releasing stock twice.
        latest = orders.find_one({"_id": document["_id"], "business_id": business["id"]})
        if latest and latest.get("status") == status:
            _dispatch_outbox_source("jumuiya_orders", business["id"], document["_id"])
            return serialise(latest)
        raise APIError(
            "The order changed while this update was being saved. Reload and retry.",
            409,
            "order_state_conflict",
        )

    _dispatch_outbox_source("jumuiya_orders", business["id"], document["_id"])
    log_action(user_id, "order.status_updated", "order", order_id_string, {
        "from": previous_status,
        "to": status,
        "inventory_status": updated.get("inventory_status"),
    })
    return serialise(updated)


# =========================================================
# SALES
# =========================================================


def _sale_fingerprint(payload):
    """Fingerprint business intent, deliberately excluding client totals/prices."""
    order_id = str(payload.get("order_id") or "")
    items = []
    if not order_id:
        for item in payload.get("items", []) or []:
            try:
                quantity = Decimal(str(item.get("quantity")))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Sale quantity is invalid.", 422, "invalid_sale_quantity")
            if not quantity.is_finite() or quantity <= 0:
                raise APIError("Sale quantities must be positive finite numbers.", 422, "invalid_sale_quantity")
            items.append({
                "product_id": str(item.get("product_id") or ""),
                "quantity": format(quantity.normalize(), "f"),
            })
    canonical = {
        "order_id": order_id,
        "customer_id": str(payload.get("customer_id") or ""),
        "items": items,
        "payment_method": str(payload.get("payment_method") or "cash").lower(),
        "reference": str(payload.get("reference") or "").strip(),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sale_payment_state(payment_method):
    """Return honest manual-entry state; no method here means provider-verified."""
    method = str(payment_method or "cash").strip().lower()
    if method == "cash":
        return "manual_attested", "manual_attested"
    if method in {"mpesa", "mobile_money", "card", "bank"}:
        return "verification_required", "unverified_manual"
    return "manual_recorded", "unverified_manual"


def _apply_sale_payment_state(sale, user_id):
    """Repair the order's payment projection after an interrupted sale write."""
    order_id = sale.get("order_id")
    if not order_id:
        return
    sale_id = str(sale.get("_id") or sale.get("id") or "")
    recorded_at = sale.get("created_at") or now_utc()
    event = {
        "event_id": "manual-sale:" + sale_id,
        "source": "manual_sale_record",
        "status": sale.get("payment_status", "manual_recorded"),
        "verification_status": sale.get("payment_verification_status", "unverified_manual"),
        "payment_method": sale.get("payment_method", "cash"),
        "reference": sale.get("reference", ""),
        "recorded_at": recorded_at,
        "actor_user_id": str(user_id),
    }
    business_id = str(sale.get("business_id") or "")
    payment_event_manifest = _build_outbox_manifest(
        event_key=f"order:{order_id}:payment-recorded:{sale_id}",
        event_type="order.payment_recorded",
        entity_type="order",
        entity_id=order_id,
        payload={
            "payment_status": sale.get("payment_status", "manual_recorded"),
            "payment_verification_status": sale.get("payment_verification_status", "unverified_manual"),
            "payment_method": sale.get("payment_method", "cash"),
            "amount_minor": sale.get("amount_minor", 0),
            "currency": sale.get("currency", "KES"),
        },
        actor_user_id=user_id,
        occurred_at=recorded_at,
    )
    collection("jumuiya_orders").update_one(
        {
            "_id": clean_id(order_id),
            "business_id": business_id,
        },
        {
            "$set": {
                "payment_status": sale.get("payment_status", "manual_recorded"),
                "payment_method": sale.get("payment_method", "cash"),
                "payment_reference": sale.get("reference", ""),
                "payment_verification_status": sale.get("payment_verification_status", "unverified_manual"),
                "payment_recorded_at": recorded_at,
                "updated_at": now_utc(),
            },
            "$addToSet": {
                "payment_history": event,
                "outbox_event_manifest": payment_event_manifest,
            },
        },
    )
    _dispatch_outbox_source("jumuiya_orders", business_id, clean_id(order_id))


def _order_sale_amount(order):
    """Use a server-held total snapshot, recomputing only for legacy orders lacking it."""
    if order.get("total_amount_minor") is not None:
        try:
            minor = int(order["total_amount_minor"])
            if minor < 0:
                raise ValueError
            return minor, minor / 100
        except (TypeError, ValueError, OverflowError):
            raise APIError("Stored order total is invalid.", 409, "invalid_order_amount")

    items = order.get("items") if isinstance(order.get("items"), list) else []
    if items and all(
        item.get("unit_price") is not None and item.get("quantity") is not None
        for item in items
    ):
        total = Decimal("0.00")
        for item in items:
            try:
                price = Decimal(str(item.get("unit_price")))
                quantity = Decimal(str(item.get("quantity")))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Stored order line is invalid.", 409, "invalid_order_amount")
            if not price.is_finite() or price < 0 or not quantity.is_finite() or quantity <= 0:
                raise APIError("Stored order line is invalid.", 409, "invalid_order_amount")
            line_total = (price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * quantity).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total += line_total
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        minor = int(total * 100)
        return minor, float(total)

    try:
        legacy_total = Decimal(str(order.get("total_amount", 0)))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError("Stored order total is invalid.", 409, "invalid_order_amount")
    if not legacy_total.is_finite() or legacy_total < 0:
        raise APIError("Stored order total is invalid.", 409, "invalid_order_amount")
    legacy_total = legacy_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    minor = int(legacy_total * 100)
    return minor, float(legacy_total)


def _complete_order_for_manual_sale(order, user_id):
    """Ensure the canonical order's inventory lifecycle completes before recording a sale."""
    order_id = str(order.get("_id") or order.get("id") or "")
    status = str(order.get("status") or "pending").lower()

    if status == "cancelled":
        raise APIError("A cancelled order cannot be recorded as a sale.", 409, "cancelled_order_sale")
    if status == "pending":
        order = update_order_status(user_id, order_id, "confirmed")
        status = str(order.get("status") or "").lower()
    if status == "confirmed":
        order = update_order_status(user_id, order_id, "processing")
        status = str(order.get("status") or "").lower()
    elif status == "processing":
        # Repair a prior interrupted reservation-consumption step safely.
        _consume_order_inventory(order, user_id)
        order = collection("jumuiya_orders").find_one({
            "_id": clean_id(order_id),
            "business_id": str(order.get("business_id") or ""),
        }) or order

    status = str(order.get("status") or status).lower()
    if status == "processing":
        order = update_order_status(user_id, order_id, "completed")
    elif status != "completed":
        raise APIError("Order is not in a saleable lifecycle state.", 409, "invalid_sale_order_state")

    if order.get("inventory_status") != "consumed":
        order = collection("jumuiya_orders").find_one({
            "_id": clean_id(order_id),
            "business_id": str(order.get("business_id") or ""),
        }) or order
    if order.get("inventory_status") != "consumed":
        raise APIError(
            "Order inventory has not been consumed. Reconcile the order before recording the sale.",
            409,
            "order_inventory_not_consumed",
        )
    return order


def record_sale(user_id, payload):
    """Record a manual sale through the canonical order/inventory lifecycle.

    The submitted amount, unit price, item name and currency are not trusted.
    Provider payment is never considered verified by this manual endpoint.
    """
    business = _require_business(user_id)
    business_id = str(business["id"])
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", idempotency_key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")

    fingerprint = _sale_fingerprint(payload)
    sales = collection("jumuiya_sales")

    if idempotency_key:
        existing = sales.find_one({
            "business_id": business_id,
            "idempotency_key": idempotency_key,
        })
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError(
                    "This Idempotency-Key was already used for a different sale payload.",
                    409,
                    "idempotency_key_reused",
                )
            _apply_sale_payment_state(existing, user_id)
            _dispatch_outbox_source("jumuiya_sales", business_id, existing["_id"])
            return serialise(existing)

    customer_id = payload.get("customer_id")
    if customer_id:
        customer = collection("jumuiya_customers").find_one({
            "_id": clean_id(customer_id),
            "business_id": business_id,
        })
        if not customer:
            raise APIError("Customer does not belong to this business.", 422, "invalid_customer")

    orders = collection("jumuiya_orders")
    order = None
    if payload.get("order_id"):
        order = orders.find_one({
            "_id": clean_id(payload["order_id"]),
            "business_id": business_id,
        })
        if not order:
            raise APIError("Order not found.", 404, "order_not_found")
        if customer_id and str(order.get("customer_id") or "") != str(customer_id):
            raise APIError("Sale customer does not match the order customer.", 409, "sale_customer_mismatch")
        customer_id = order.get("customer_id")

    if order is not None:
        order_id = str(order.get("_id") or order.get("id") or "")
        existing_for_order = sales.find_one({
            "business_id": business_id,
            "order_id": order_id,
            "canonical_order_sale": True,
        })
        if existing_for_order:
            if existing_for_order.get("request_fingerprint") != fingerprint:
                raise APIError(
                    "A sale has already been recorded for this order with different details.",
                    409,
                    "sale_already_recorded",
                )
            _apply_sale_payment_state(existing_for_order, user_id)
            _dispatch_outbox_source("jumuiya_sales", business_id, existing_for_order["_id"])
            return serialise(existing_for_order)
    else:
        submitted_items = payload.get("items")
        if not isinstance(submitted_items, list) or not submitted_items:
            raise APIError("A sale must contain at least one item or an existing order_id.", 422, "invalid_sale_items")
        order_request = {
            "customer_id": str(customer_id) if customer_id else None,
            "items": submitted_items,
            "notes": "POS sale" + (": " + str(payload.get("reference")) if payload.get("reference") else ""),
            "source_channel": "pos",
        }
        if idempotency_key:
            # Stable internal key so a retry can recover an order created before
            # the sale document itself was persisted.
            order_request["idempotency_key"] = "pos-order-" + hashlib.sha256(
                (business_id + ":" + idempotency_key).encode("utf-8")
            ).hexdigest()
        order = create_order(user_id, order_request)
        # serialise() changes _id to id; load the canonical Mongo document again.
        order = orders.find_one({
            "_id": clean_id(order.get("id")),
            "business_id": business_id,
        }) or order

    order_id = str(order.get("_id") or order.get("id") or "")
    existing_for_order = sales.find_one({
        "business_id": business_id,
        "order_id": order_id,
        "canonical_order_sale": True,
    })
    if existing_for_order:
        if existing_for_order.get("request_fingerprint") != fingerprint:
            raise APIError(
                "A sale has already been recorded for this order with different details.",
                409,
                "sale_already_recorded",
            )
        _apply_sale_payment_state(existing_for_order, user_id)
        return serialise(existing_for_order)

    # A completed order is still subject to the same inventory audit invariant.
    order = _complete_order_for_manual_sale(order, user_id)
    order_id = str(order.get("_id") or order.get("id") or "")
    amount_minor, amount = _order_sale_amount(order)
    currency = str(order.get("currency") or business.get("currency") or "KES").upper()
    payment_status, verification_status = _sale_payment_state(payload.get("payment_method", "cash"))
    now = now_utc()

    sale_payload_data = {
        "order_id": order_id,
        "customer_id": str(customer_id) if customer_id else None,
        "items": order.get("items") or [],
        "amount": amount,
        "currency": currency,
        "payment_method": payload.get("payment_method", "cash"),
        "reference": str(payload.get("reference") or "")[:120],
    }
    document = sale_document(business_id, sale_payload_data)
    document["_id"] = ObjectId()
    document.update({
        "order_id": order_id,
        "amount_minor": amount_minor,
        "currency": currency,
        "source_channel": order.get("source_channel") or "pos",
        "canonical_order_sale": True,
        "request_fingerprint": fingerprint,
        "payment_status": payment_status,
        "payment_verification_status": verification_status,
        "payment_recorded_at": now,
        "payment_source": "manual_sale_record",
        "provider_verified": False,
        "recorded_by_user_id": str(user_id),
    })
    if idempotency_key:
        document["idempotency_key"] = idempotency_key

    sale_event_manifest = _build_outbox_manifest(
        event_key=f"sale:{document['_id']}:created",
        event_type="sale.created",
        entity_type="sale",
        entity_id=document["_id"],
        payload={
            "order_id": order_id,
            "sale_id": str(document["_id"]),
            "amount_minor": amount_minor,
            "currency": currency,
            "payment_status": payment_status,
            "payment_verification_status": verification_status,
            "payment_method": document.get("payment_method", "cash"),
            "source_channel": document["source_channel"],
        },
        actor_user_id=user_id,
        occurred_at=document.get("created_at") or now,
    )
    document["outbox_event_manifest"] = [sale_event_manifest]
    document["outbox_enqueued_event_keys"] = []

    try:
        result = sales.insert_one(document)
        document["_id"] = result.inserted_id
    except DuplicateKeyError:
        existing = None
        if idempotency_key:
            existing = sales.find_one({
                "business_id": business_id,
                "idempotency_key": idempotency_key,
            })
        if existing is None:
            existing = sales.find_one({
                "business_id": business_id,
                "order_id": order_id,
                "canonical_order_sale": True,
            })
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError("Sale already exists with different details.", 409, "sale_already_recorded")
            _apply_sale_payment_state(existing, user_id)
            _dispatch_outbox_source("jumuiya_sales", business_id, existing["_id"])
            return serialise(existing)
        raise

    _apply_sale_payment_state(document, user_id)
    _dispatch_outbox_source("jumuiya_sales", business_id, document["_id"])
    log_action(user_id, "sale.created", "sale", document["_id"], {
        "order_id": order_id,
        "amount_minor": amount_minor,
        "payment_status": payment_status,
        "payment_verification_status": verification_status,
    })
    return serialise(document)


# =========================================================
# EXPENSES
# =========================================================


def _post_expense_journal(document, user_id):
    """Post the expense while leaving its funding/settlement classification explicit."""
    amount_minor = int(document.get("amount_minor", 0) or 0)
    if amount_minor <= 0:
        return None
    # Lazy import prevents the finance blueprint package from creating a
    # module-import cycle with the existing Biashara service module.
    from backend.jumuiya.biashara.finance.ledger import post_journal_entry

    expense_id = str(document.get("_id") or document.get("id") or "")
    return post_journal_entry(
        business_id=str(document.get("business_id") or ""),
        source_key="expense-recorded:" + expense_id,
        source_type="expense.recorded",
        source_id=expense_id,
        currency=document.get("currency", "KES"),
        lines=[
            {
                "account_code": "operating_expense",
                "debit_minor": amount_minor,
                "credit_minor": 0,
                "memo": str(document.get("category") or "Operating expense")[:300],
            },
            {
                "account_code": "expense_settlement_unclassified",
                "debit_minor": 0,
                "credit_minor": amount_minor,
                "memo": "Expense funding or payable requires settlement classification",
            },
        ],
        actor_user_id=user_id,
        basis="Expense recorded as incurred; payment method/funding source was not supplied. Offset remains unclassified pending reconciliation.",
        effective_at=document.get("spent_at") or document.get("created_at") or now_utc(),
    )


def create_expense(user_id, payload):
    """Record an expense with safe retries, an outbox intent and a provisional journal."""
    business = _require_business(user_id)
    business_id = str(business["id"])
    key = str(payload.get("idempotency_key") or "").strip()
    if key and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")

    try:
        amount = Decimal(str(payload.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError("Expense amount is invalid.", 422, "invalid_expense_amount")
    if not amount.is_finite() or amount < 0:
        raise APIError("Expense amount must be non-negative and finite.", 422, "invalid_expense_amount")
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amount_minor = int(amount * 100)

    currency = str(payload.get("currency") or business.get("currency") or "KES").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise APIError("Expense currency must be a 3-letter ISO currency code.", 422, "invalid_expense_currency")

    stable_payload = {
        "title": str(payload.get("title") or "").strip()[:160],
        "category": str(payload.get("category") or "").strip()[:120],
        "amount_minor": amount_minor,
        "currency": currency,
        "notes": str(payload.get("notes") or "").strip()[:1000],
    }
    fingerprint = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    expenses = collection("jumuiya_expenses")
    if key:
        existing = expenses.find_one({"business_id": business_id, "idempotency_key": key})
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError("Idempotency-Key was reused for different expense data.", 409, "idempotency_key_reused")
            _dispatch_outbox_source("jumuiya_expenses", business_id, existing["_id"])
            _post_expense_journal(existing, user_id)
            return serialise(existing)

    document = expense_document(
        business_id,
        {
            **payload,
            **stable_payload,
            "amount": float(amount),
            "currency": currency,
        },
    )
    document["_id"] = ObjectId()
    document.update({
        "amount_minor": amount_minor,
        "currency": currency,
        "accounting_status": "provisional_unclassified",
        "tax_status": "not_configured",
        "idempotency_key": key or None,
        "request_fingerprint": fingerprint,
        "outbox_enqueued_event_keys": [],
    })
    event = _build_outbox_manifest(
        event_key=f"expense:{document['_id']}:recorded",
        event_type="expense.recorded",
        entity_type="expense",
        entity_id=document["_id"],
        payload={
            "status": "recorded",
            "expense_id": str(document["_id"]),
            "expense_category": stable_payload["category"][:200],
            "amount_minor": amount_minor,
            "currency": currency,
        },
        actor_user_id=user_id,
        occurred_at=document.get("spent_at") or document.get("created_at") or now_utc(),
    )
    document["outbox_event_manifest"] = [event]

    try:
        expenses.insert_one(document)
    except DuplicateKeyError:
        if key:
            existing = expenses.find_one({"business_id": business_id, "idempotency_key": key})
            if existing and existing.get("request_fingerprint") == fingerprint:
                _dispatch_outbox_source("jumuiya_expenses", business_id, existing["_id"])
                _post_expense_journal(existing, user_id)
                return serialise(existing)
            if existing:
                raise APIError("Idempotency-Key was reused for different expense data.", 409, "idempotency_key_reused")
        raise

    _dispatch_outbox_source("jumuiya_expenses", business_id, document["_id"])
    _post_expense_journal(document, user_id)
    log_action(user_id, "expense.created", "expense", document["_id"], {
        "amount_minor": amount_minor,
        "currency": currency,
        "accounting_status": document["accounting_status"],
    })
    return serialise(document)

def list_expenses(
    user_id,
):

    business = _require_business(
        user_id
    )

    documents = (
        collection(
            "jumuiya_expenses"
        )
        .find({
            "business_id": business["id"]
        })
        .sort(
            "spent_at",
            -1,
        )
    )

    return serialise_many(
        documents
    )


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(
    user_id,
):

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    products = collection(
        "jumuiya_products"
    )

    orders = collection(
        "jumuiya_orders"
    )

    sales = collection(
        "jumuiya_sales"
    )

    expenses = collection(
        "jumuiya_expenses"
    )

    customers = collection(
        "jumuiya_customers"
    )

    # -----------------------------------------------------
    # SALES
    # -----------------------------------------------------

    sales_result = list(
        sales.aggregate([
            {
                "$match": {
                    "business_id": business_id
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": "$amount"
                    }
                }
            },
        ])
    )

    # -----------------------------------------------------
    # EXPENSES
    # -----------------------------------------------------

    expenses_result = list(
        expenses.aggregate([
            {
                "$match": {
                    "business_id": business_id
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": "$amount"
                    }
                }
            },
        ])
    )

    total_sales = (
        float(
            sales_result[0]["total"]
        )
        if sales_result
        else 0.0
    )

    total_expenses = (
        float(
            expenses_result[0]["total"]
        )
        if expenses_result
        else 0.0
    )

    # -----------------------------------------------------
    # COUNTS
    # -----------------------------------------------------

    product_count = products.count_documents({
        "business_id": business_id,
        "status": {
            "$ne": "deleted"
        },
    })

    low_stock_count = products.count_documents({
        "business_id": business_id,
        "status": "active",
        "stock_quantity": {
            "$lte": 5
        },
    })

    customer_count = customers.count_documents({
        "business_id": business_id
    })

    pending_orders = orders.count_documents({
        "business_id": business_id,
        "status": {
            "$in": [
                "pending",
                "confirmed",
                "processing",
            ]
        },
    })

    completed_orders = orders.count_documents({
        "business_id": business_id,
        "status": "completed",
    })

    return {
        "business": business,

        "metrics": {
            "products": product_count,
            "low_stock": low_stock_count,
            "customers": customer_count,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,

            "sales_total": total_sales,

            "expenses_total": total_expenses,

            "net_estimate": (
                total_sales
                - total_expenses
            ),
        },
    }

# =========================================================
# BUSINESS WEBSITE / PUBLIC STOREFRONT
# =========================================================


def get_biashara_website_settings(user_id):
    business = _require_business(user_id)
    settings = dict(DEFAULT_BIASHARA_WEBSITE_SETTINGS)
    stored = business.get("website")
    if isinstance(stored, dict):
        settings.update(stored)
    return {
        "slug": business.get("slug", ""),
        "url_path": "/b/" + str(business.get("slug", "")),
        "settings": settings,
    }


def save_biashara_website_settings(user_id, payload):
    business = _require_business(user_id)
    now = now_utc()
    current = business.get("website") if isinstance(business.get("website"), dict) else {}
    settings = normalize_biashara_website_settings(payload, current)
    settings["updated_at"] = now.isoformat()
    if settings.get("published"):
        settings["published_at"] = settings.get("published_at") or now.isoformat()
    else:
        settings["published_at"] = None

    collection("jumuiya_businesses").update_one(
        {"_id": clean_id(business["id"])},
        {"$set": {"website": settings, "updated_at": now}},
    )
    log_action(user_id, "business.website_updated", "business", clean_id(business["id"]))
    return {
        "slug": business.get("slug", ""),
        "url_path": "/b/" + str(business.get("slug", "")),
        "settings": settings,
    }


def get_public_biashara_website(slug):
    normalized_slug = str(slug or "").strip().lower()
    if not normalized_slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized_slug):
        raise APIError("Business website not found.", 404, "website_not_found")

    business = collection("jumuiya_businesses").find_one({
        "slug": normalized_slug,
        "status": "active",
        "website.published": True,
    })
    if not business:
        raise APIError("Business website not found or not published.", 404, "website_not_found")

    website = business.get("website") if isinstance(business.get("website"), dict) else {}
    public_business = {
        "name": business.get("name", ""),
        "slug": business.get("slug", ""),
        "description": business.get("description", ""),
        "phone": business.get("phone", "") if website.get("contact_enabled", True) is True else "",
        "email": business.get("email", "") if website.get("contact_enabled", True) is True else "",
        "location": business.get("location", ""),
        "county": business.get("county", ""),
        "currency": business.get("currency", "KES") or "KES",
        "logo_url": business.get("logo_url", ""),
    }
    public_website = {
        "headline": website.get("headline") or business.get("name", ""),
        "tagline": website.get("tagline", ""),
        "about": website.get("about") or business.get("description", ""),
        "hero_image_url": website.get("hero_image_url", ""),
        "primary_color": website.get("primary_color", "#1d4ed8"),
        "accent_color": website.get("accent_color", "#0f766e"),
        "seo_title": website.get("seo_title") or business.get("name", ""),
        "seo_description": website.get("seo_description") or business.get("description", ""),
        "whatsapp_number": website.get("whatsapp_number", "") if website.get("contact_enabled", True) is True else "",
        "show_products": website.get("show_products", True) is True,
        "contact_enabled": website.get("contact_enabled", True) is True,
    }

    products = []
    if public_website["show_products"]:
        product_docs = collection("jumuiya_products").find(
            {
                "business_id": str(business["_id"]),
                "status": "active",
            },
            {
                "_id": 1,
                "name": 1,
                "description": 1,
                "category": 1,
                "price": 1,
                "currency": 1,
                "image_url": 1,
                "stock_quantity": 1,
            },
        ).sort("created_at", -1).limit(60)
        for product in product_docs:
            products.append({
                "id": str(product.get("_id", "")),
                "name": product.get("name", ""),
                "description": product.get("description", ""),
                "category": product.get("category", ""),
                "price": product.get("price", 0),
                "currency": product.get("currency") or public_business["currency"],
                "image_url": product.get("image_url", ""),
                "available": (
                    float(product.get("stock_quantity", 0) or 0)
                    - float(product.get("reserved_quantity", 0) or 0)
                ) > 0,
            })

    return {
        "business": public_business,
        "website": public_website,
        "products": products,
    }


def submit_public_biashara_inquiry(slug, payload):
    if not isinstance(payload, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")

    # Low-cost honeypot: automated submissions that fill this field are accepted
    # without creating a lead. Production should also enable request rate limits.
    if str(payload.get("website", "")).strip():
        return {"accepted": True}

    normalized_slug = str(slug or "").strip().lower()
    business = collection("jumuiya_businesses").find_one({
        "slug": normalized_slug,
        "status": "active",
        "website.published": True,
        "website.contact_enabled": True,
    })
    if not business:
        raise APIError("Business website not found or contact is disabled.", 404, "website_not_found")

    def text_field(name, limit, required=False):
        value = payload.get(name, "")
        if not isinstance(value, str):
            raise APIError(name.replace("_", " ").capitalize() + " must be text.", 422, "validation_error")
        value = value.strip()
        if required and not value:
            raise APIError(name.replace("_", " ").capitalize() + " is required.", 422, "validation_error")
        if len(value) > limit:
            raise APIError(name.replace("_", " ").capitalize() + " is too long.", 422, "validation_error")
        if "<" in value or ">" in value:
            raise APIError("HTML is not allowed in inquiry fields.", 422, "invalid_inquiry_text")
        return value

    name = text_field("name", 80, True)
    email = text_field("email", 254)
    phone = text_field("phone", 32)
    message = text_field("message", 2000, True)
    if not email and not phone:
        raise APIError("Provide an email address or phone number.", 422, "contact_required")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise APIError("Enter a valid email address.", 422, "invalid_email")
    if phone and not re.fullmatch(r"[+0-9() .-]{7,32}", phone):
        raise APIError("Enter a valid phone number.", 422, "invalid_phone")

    now = now_utc()
    document = {
        "business_id": str(business["_id"]),
        "owner_user_id": str(business.get("owner_user_id", "")),
        "business_slug": normalized_slug,
        "source": "public_website",
        "name": name,
        "email": email,
        "phone": phone,
        "message": message,
        "status": "new",
        "created_at": now,
        "updated_at": now,
    }
    collection("jumuiya_business_website_inquiries").insert_one(document)
    return {"accepted": True}


def list_biashara_website_inquiries(user_id, limit=30):
    business = _require_business(user_id)
    documents = collection("jumuiya_business_website_inquiries").find(
        {
            "business_id": business["id"],
            "owner_user_id": str(user_id),
        }
    ).sort("created_at", -1).limit(_bounded_list_limit(limit))
    return serialise_many(documents)
