# backend/jumuiya/elimu/inventory/routes.py
"""Authenticated endpoints for school stock and Principal-approved needs."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from . import services

inventory_bp = Blueprint("jumuiya_elimu_inventory", __name__, url_prefix="/inventory")


def _body() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise APIError("A JSON object is required.", 400, "invalid_json")
    return value


@inventory_bp.get("/items")
@require_authenticated
def get_items():
    return ok(services.list_items(current_user_id()))


@inventory_bp.post("/items")
@require_authenticated
def post_item():
    return created(services.create_item(current_user_id(), _body()), "Inventory item created.")


@inventory_bp.patch("/items/<item_id>")
@require_authenticated
def patch_item(item_id: str):
    return ok(services.update_item(current_user_id(), item_id, _body()), "Inventory item updated.")


@inventory_bp.post("/movements")
@require_authenticated
def post_movement():
    return created(services.record_movement(current_user_id(), _body()), "Stock movement recorded.")


@inventory_bp.get("/needs")
@require_authenticated
def get_needs():
    return ok(services.list_needs(current_user_id()))


@inventory_bp.post("/needs")
@require_authenticated
def post_need():
    return created(services.create_need(current_user_id(), _body()), "Supply request submitted to the Principal for approval.")


@inventory_bp.post("/needs/<need_id>/decision")
@require_authenticated
def decide_need(need_id: str):
    result = services.decide_need(current_user_id(), need_id, _body())
    warning = result.pop("warning", None)
    message = "Supply request reviewed."
    if warning:
        result["warning"] = warning
    return ok(result, message)
