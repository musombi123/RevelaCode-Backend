"""Biashara integration readiness diagnostics.

This module reports configuration and certification gates without exposing
secrets or claiming an external provider is live merely because keys exist.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from flask import Blueprint

from backend.jumuiya.biashara.services import _require_business
from backend.jumuiya.biashara.payments import _configuration_status as mpesa_configuration_status
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import ok


integrations_bp = Blueprint("jumuiya_biashara_integrations", __name__)


def _https_endpoint(value):
    try:
        parsed = urlsplit(str(value or "").strip())
        return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment
    except ValueError:
        return False


def _etims_status():
    mode = os.getenv("BIASHARA_ETIMS_MODE", "").strip().lower()
    adapter = os.getenv("BIASHARA_ETIMS_ADAPTER", "").strip().lower()
    endpoint = os.getenv("BIASHARA_ETIMS_BASE_URL", "").strip()
    certification_reference = os.getenv("BIASHARA_ETIMS_CERTIFICATION_REFERENCE", "").strip()
    certified = os.getenv("BIASHARA_ETIMS_CERTIFIED", "").strip().lower() == "true"
    checks = {
        "mode_selected": mode in {"sandbox", "production"},
        "adapter_selected": adapter in {"oscu", "vscu"},
        "https_endpoint": _https_endpoint(endpoint),
        "certification_reference_present": bool(certification_reference),
        "certification_flag": certified,
    }
    production_ready = all(checks.values()) and mode == "production"
    if production_ready:
        state = "production_configuration_ready"
    elif mode == "sandbox" and adapter in {"oscu", "vscu"} and _https_endpoint(endpoint):
        state = "sandbox_configuration"
    elif any((mode, adapter, endpoint, certification_reference, certified)):
        state = "certification_pending"
    else:
        state = "not_configured"
    return {
        "provider": "KRA eTIMS",
        "state": state,
        "mode": mode or None,
        "adapter": adapter or None,
        "checks": checks,
        "blockers": [key for key, valid in checks.items() if not valid],
        "submission_enabled": False,
        "note": "No tax invoice is submitted or marked accepted by this readiness endpoint. OSCU/VSCU system-to-system production use remains gated by the relevant KRA testing, vetting and certification process.",
    }


def _whatsapp_status():
    checks = {
        "access_token_present": bool(os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()),
        "phone_number_id_present": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()),
        "app_secret_present": bool(os.getenv("WHATSAPP_APP_SECRET", "").strip()),
        "webhook_verify_token_present": bool(os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()),
    }
    configured = all(checks.values())
    return {
        "provider": "WhatsApp Cloud API",
        "state": "configuration_present" if configured else "not_configured",
        "checks": checks,
        "blockers": [key for key, valid in checks.items() if not valid],
        "business_commands_enabled": False,
        "note": "Meta credentials being present does not mean Biashara employee verification or the sales-report command handler is active.",
    }


@integrations_bp.get("/integrations/status")
@require_authenticated
def integration_status():
    _require_business(str(current_user_id()), permission="integrations.view")
    return ok({
        "mpesa": mpesa_configuration_status(),
        "etims": _etims_status(),
        "whatsapp": _whatsapp_status(),
    }, "Biashara integration readiness loaded.")
