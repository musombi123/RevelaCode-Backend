"""Authenticated configuration API for Biashara provider connections."""
from __future__ import annotations

from flask import Blueprint, Response, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.tenancy.service import require_business_permission
from backend.jumuiya.biashara.integrations import service
from backend.jumuiya.biashara.integrations import webhooks


biashara_integrations_bp = Blueprint("jumuiya_biashara_integrations", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


@biashara_integrations_bp.get("")
@require_authenticated
@require_business_permission("integration.view")
def get_connections():
    rows = service.list_connections(current_user_id())
    return ok(rows, "Integration connection configuration loaded.", meta={"count": len(rows)})


@biashara_integrations_bp.post("")
@require_authenticated
@require_business_permission("integration.manage")
def post_connection():
    result = service.create_connection(current_user_id(), _body())
    return created(result, "Integration credentials stored encrypted. Provider connectivity has not been tested.")


@biashara_integrations_bp.patch("/<connection_id>")
@require_authenticated
@require_business_permission("integration.manage")
def patch_connection(connection_id):
    result = service.update_connection(current_user_id(), connection_id, _body())
    return ok(result, "Integration configuration updated. Provider connectivity has not been tested.")


@biashara_integrations_bp.patch("/<connection_id>/enabled")
@require_authenticated
@require_business_permission("integration.manage")
def patch_connection_enabled(connection_id):
    payload = _body()
    if "enabled" not in payload or not isinstance(payload["enabled"], bool):
        raise APIError("enabled must be a boolean.", 422, "invalid_integration_configuration")
    result = service.set_connection_enabled(current_user_id(), connection_id, payload["enabled"])
    return ok(result, "Integration connection state saved; this does not confirm provider connectivity.")

@biashara_integrations_bp.delete("/<connection_id>")
@require_authenticated
@require_business_permission("integration.manage")
def delete_connection(connection_id):
    result = service.delete_connection(current_user_id(), connection_id)
    return ok(result, "Integration connection and its encrypted credentials were removed.")

@biashara_integrations_bp.get("/webhook-deliveries")
@require_authenticated
@require_business_permission("integration.view")
def get_webhook_deliveries():
    rows = webhooks.list_webhook_deliveries(
        current_user_id(),
        limit=request.args.get("limit", 50),
        status=request.args.get("status"),
        provider=request.args.get("provider"),
    )
    return ok(rows, "Verified integration webhook inbox loaded.", meta={"count": len(rows)})


@biashara_integrations_bp.get("/<connection_id>/webhook")
def verify_whatsapp_webhook(connection_id):
    challenge = webhooks.verify_whatsapp_challenge(
        connection_id,
        request.args.get("hub.mode"),
        request.args.get("hub.verify_token"),
        request.args.get("hub.challenge"),
    )
    return Response(challenge, status=200, mimetype="text/plain")


@biashara_integrations_bp.post("/<connection_id>/webhook")
def receive_provider_webhook(connection_id):
    if request.content_length is not None and request.content_length > webhooks.MAX_WEBHOOK_BODY_BYTES:
        raise APIError("Webhook body exceeds the allowed size.", 413, "webhook_body_too_large")
    raw_body = request.get_data(cache=False, as_text=False)
    result = webhooks.receive_webhook(connection_id, raw_body, request.headers)
    return ok(result, "Webhook signature verified and event safely queued for review.")

