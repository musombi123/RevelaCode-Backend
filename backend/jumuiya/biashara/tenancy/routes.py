"""Multi-business selector and staff membership API for Biashara."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara import schemas
from backend.jumuiya.biashara.tenancy import service


biashara_tenancy_bp = Blueprint("jumuiya_biashara_tenancy", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


def _validate(schema, payload):
    try:
        return schema(payload)
    except ValueError as error:
        raise APIError(str(error), 422, "validation_error")


@biashara_tenancy_bp.get("/businesses")
@require_authenticated
def get_businesses():
    rows = service.list_accessible_businesses(current_user_id())
    return ok(rows, "Accessible Biashara businesses loaded.", meta={"count": len(rows)})


@biashara_tenancy_bp.post("/businesses")
@require_authenticated
def post_business():
    payload = _validate(schemas.business_payload, _body())
    business = service.create_business(current_user_id(), payload)
    return created(business, "Additional Biashara business created.")


@biashara_tenancy_bp.get("/businesses/<business_id>/members")
@require_authenticated
def get_business_members(business_id):
    rows = service.list_members(current_user_id(), business_id)
    return ok(rows, "Business team members loaded.", meta={"count": len(rows)})


@biashara_tenancy_bp.post("/businesses/<business_id>/members")
@require_authenticated
def post_business_member(business_id):
    payload = _body()
    member = service.add_member(
        current_user_id(),
        business_id,
        payload.get("user_id"),
        payload.get("role"),
    )
    return created(member, "Existing verified RevelaCode user added to the business team.")


@biashara_tenancy_bp.delete("/businesses/<business_id>/members/<member_user_id>")
@require_authenticated
def delete_business_member(business_id, member_user_id):
    result = service.remove_member(current_user_id(), business_id, member_user_id)
    return ok(result, "Business membership revoked.")
