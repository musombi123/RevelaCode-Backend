# backend/jumuiya/core/responses.py

from flask import jsonify


# =========================================================
# SUCCESS RESPONSE
# =========================================================

def ok(
    data=None,
    message=None,
    status_code=200,
    meta=None,
):
    """
    Standard Jumuiya success response.

    Example:

    {
        "success": true,
        "message": "Business loaded.",
        "data": {...},
        "meta": {...}
    }
    """

    payload = {
        "success": True,
    }

    if message is not None:
        payload["message"] = message

    if data is not None:
        payload["data"] = data

    if meta is not None:
        payload["meta"] = meta

    return jsonify(payload), status_code


# =========================================================
# CREATED
# =========================================================

def created(
    data=None,
    message="Created successfully",
):
    """
    Standard 201 response.
    """

    return ok(
        data=data,
        message=message,
        status_code=201,
    )


# =========================================================
# UPDATED
# =========================================================

def updated(
    data=None,
    message="Updated successfully",
):
    """
    Standard response for resource updates.
    """

    return ok(
        data=data,
        message=message,
        status_code=200,
    )


# =========================================================
# DELETED
# =========================================================

def deleted(
    data=None,
    message="Deleted successfully",
):
    """
    Standard response for resource deletion/archive.
    """

    return ok(
        data=data,
        message=message,
        status_code=200,
    )


# =========================================================
# PAGINATED RESPONSE
# =========================================================

def paginated(
    data,
    page,
    per_page,
    total,
    message=None,
):
    """
    Standard response for paginated resources.

    This will become useful for:
        - Marketplace
        - Community
        - Products
        - Orders
        - Notifications
        - Messages
    """

    page = max(
        int(page),
        1,
    )

    per_page = max(
        int(per_page),
        1,
    )

    total = max(
        int(total),
        0,
    )

    total_pages = (
        (total + per_page - 1)
        // per_page
        if total
        else 0
    )

    meta = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }

    return ok(
        data=data,
        message=message,
        status_code=200,
        meta=meta,
    )