"""Safe WooCommerce connection checks and explicit catalogue import.

Only the owner-selected HTTPS WooCommerce store is queried. Requests do not
follow redirects; resolved IPs are checked before each call; credentials stay
inside the encrypted integration registry. Import is opt-in, tenant-scoped and
idempotent. Stock and cost price are deliberately not imported in this slice:
stock needs a separate source-of-truth/reconciliation decision.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import secrets
import socket
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara import services as biashara_services
from backend.jumuiya.biashara.integrations import service as integration_service
from backend.jumuiya.biashara.tenancy.service import require_permission


logger = logging.getLogger("jumuiya.biashara.woocommerce")

MAPPINGS_COLLECTION = "jumuiya_external_object_mappings"
PRODUCTS_COLLECTION = "jumuiya_products"
REQUEST_TIMEOUT = (3.05, 15)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGE_SIZE = 50
MAX_IMPORT_BATCH = 50
IMPORT_LEASE_SECONDS = 120
PRODUCT_FIELDS = (
    "id,name,slug,sku,type,status,price,regular_price,stock_status,manage_stock,"
    "stock_quantity,description,short_description,categories,images,date_modified_gmt,date_modified"
)


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _context(user_id, permission):
    context = require_permission(user_id, permission)
    business_id = str(context.get("id") or "")
    if not business_id:
        raise APIError("Selected business is unavailable.", 409, "business_id_missing")
    currency = str(context.get("currency") or "KES").upper()
    return context, business_id, currency


def _load_connection(user_id, connection_id, permission, require_enabled=True):
    context, business_id, currency = _context(user_id, permission)
    query = {
        "_id": _clean_id(connection_id),
        "business_id": business_id,
        "provider": "woocommerce",
    }
    if require_enabled:
        query["enabled"] = True
    connection = integration_service.collection(integration_service.CONNECTIONS_COLLECTION).find_one(query)
    if not connection:
        raise APIError("Enabled WooCommerce connection was not found for this business.", 404, "woocommerce_connection_not_found")

    metadata = connection.get("metadata") if isinstance(connection.get("metadata"), dict) else {}
    store_url = integration_service._validate_store_url(metadata.get("store_url"))
    api_version = str(metadata.get("api_version") or "wc/v3").strip().lower()
    if not re.fullmatch(r"wc/v[0-9]{1,2}", api_version):
        raise APIError("WooCommerce API version is not supported.", 409, "woocommerce_api_version_invalid")
    credentials = integration_service._decrypt_credentials(connection)
    consumer_key = credentials.get("consumer_key")
    consumer_secret = credentials.get("consumer_secret")
    if not isinstance(consumer_key, str) or not consumer_key or not isinstance(consumer_secret, str) or not consumer_secret:
        raise APIError("WooCommerce read credentials are incomplete.", 409, "woocommerce_credentials_incomplete")
    return {
        "business_id": business_id,
        "currency": currency,
        "connection": connection,
        "metadata": metadata,
        "store_url": store_url,
        "api_version": api_version,
        "credentials": {"consumer_key": consumer_key, "consumer_secret": consumer_secret},
    }


def _assert_public_store_host(store_url):
    """Fail closed for local/private destinations before every server-side call.

    Deployment egress rules should additionally block private, loopback and
    link-local destinations to protect against DNS rebinding after this check.
    """
    parsed = urlparse(store_url)
    host = str(parsed.hostname or "").rstrip(".").lower()
    if not host or parsed.scheme.lower() != "https":
        raise APIError("WooCommerce store must be a valid HTTPS host.", 422, "woocommerce_store_url_invalid")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
        raise APIError("WooCommerce store host is not public.", 422, "woocommerce_store_host_blocked")
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except (socket.gaierror, OSError):
            raise APIError("WooCommerce store host could not be resolved.", 502, "woocommerce_store_dns_failed")
        addresses = []
        for item in resolved:
            try:
                addresses.append(ipaddress.ip_address(item[4][0].split("%", 1)[0]))
            except (ValueError, IndexError):
                raise APIError("WooCommerce store DNS resolution returned an invalid address.", 502, "woocommerce_store_dns_invalid")
    if not addresses:
        raise APIError("WooCommerce store host did not resolve to an address.", 502, "woocommerce_store_dns_failed")
    if any(not address.is_global for address in addresses):
        raise APIError("WooCommerce store resolves to a non-public IP address.", 422, "woocommerce_store_host_blocked")
    return host


def _decode_response(response):
    status = int(getattr(response, "status_code", 0) or 0)
    if 300 <= status < 400:
        raise APIError("WooCommerce returned a redirect; redirects are blocked for security.", 502, "woocommerce_redirect_blocked")
    if status == 401:
        raise APIError("WooCommerce rejected the API credentials. Check the consumer key, secret and read permissions.", 502, "woocommerce_authentication_failed")
    if status == 403:
        raise APIError("WooCommerce denied this API operation. Check the API key permissions.", 502, "woocommerce_permission_denied")
    if status == 429:
        raise APIError("WooCommerce rate-limited this request. Retry after the provider's limit resets.", 429, "woocommerce_rate_limited")
    if status < 200 or status >= 300:
        raise APIError(
            f"WooCommerce returned HTTP {status or 'unknown'}.",
            502,
            "woocommerce_provider_http_error",
            details={"provider_http_status": status},
        )

    headers = getattr(response, "headers", {}) or {}
    try:
        declared = int(headers.get("Content-Length", "0") or 0)
    except (ValueError, TypeError):
        declared = 0
    if declared > MAX_RESPONSE_BYTES:
        raise APIError("WooCommerce response exceeded the size limit.", 502, "woocommerce_response_too_large")

    chunks = []
    length = 0
    try:
        for chunk in response.iter_content(chunk_size=32 * 1024):
            if not chunk:
                continue
            length += len(chunk)
            if length > MAX_RESPONSE_BYTES:
                raise APIError("WooCommerce response exceeded the size limit.", 502, "woocommerce_response_too_large")
            chunks.append(chunk)
        body = json.loads(b"".join(chunks).decode("utf-8"))
    except APIError:
        raise
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        raise APIError("WooCommerce returned invalid JSON.", 502, "woocommerce_response_invalid")
    return body, headers


def _api_get(config, endpoint, params=None):
    _assert_public_store_host(config["store_url"])
    relative = str(endpoint or "").strip("/")
    if not relative or ".." in relative.split("/"):
        raise APIError("WooCommerce API path is invalid.", 422, "woocommerce_api_path_invalid")
    url = (
        config["store_url"].rstrip("/")
        + "/wp-json/"
        + config["api_version"]
        + "/"
        + relative
    )
    try:
        response = requests.get(
            url,
            auth=(
                config["credentials"]["consumer_key"],
                config["credentials"]["consumer_secret"],
            ),
            headers={"Accept": "application/json"},
            params=params or {},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as error:
        raise APIError(
            "WooCommerce could not be reached. Verify the HTTPS host and provider availability.",
            502,
            "woocommerce_connection_unavailable",
            details={"error_type": type(error).__name__},
        )
    try:
        return _decode_response(response)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _store_currency(config):
    value = str((config.get("metadata") or {}).get("store_currency") or "").strip().upper()
    return value if re.fullmatch(r"[A-Z]{3}", value) else None


def _currency_check(config):
    source_currency = _store_currency(config)
    business_currency = str(config.get("currency") or "KES").upper()
    return {
        "store_currency": source_currency,
        "business_currency": business_currency,
        "configured": bool(source_currency),
        "matches_business_currency": bool(source_currency and source_currency == business_currency),
        "source": "merchant_confirmed_connection_metadata" if source_currency else "not_configured",
    }


def _mark_test_result(config, success, error_code=None, summary=None):
    connection = config["connection"]
    business_id = config["business_id"]
    now = now_utc()
    try:
        integration_service.collection(integration_service.CONNECTIONS_COLLECTION).update_one(
            {"_id": connection["_id"], "business_id": business_id, "provider": "woocommerce"},
            {"$set": {
                "last_tested_at": now,
                "last_test_status": "success" if success else "failed",
                "last_test_error_code": None if success else str(error_code or "woocommerce_connection_failed")[:100],
                "last_test_summary": str(summary or "")[:240] if success else None,
                "updated_at": now,
            }},
        )
    except Exception as error:
        logger.warning("WooCommerce connectivity audit update deferred (%s).", type(error).__name__)


def test_connection(user_id, connection_id):
    config = _load_connection(user_id, connection_id, "integration.manage", require_enabled=True)
    try:
        body, headers = _api_get(config, "products", {
            "per_page": 1,
            "page": 1,
            "status": "publish",
            "_fields": "id,name",
        })
        if not isinstance(body, list):
            raise APIError("WooCommerce product endpoint did not return a list.", 502, "woocommerce_response_invalid")
        currency = _currency_check(config)
        summary = "Read-only product endpoint succeeded."
        _mark_test_result(config, True, summary=summary)
        log_action(user_id, "biashara.woocommerce_connection_tested", "integration_connection", config["connection"]["_id"], {
            "success": True,
            "sample_count": len(body),
            "store_currency_configured": currency["configured"],
        })
        return {
            "connection_id": str(config["connection"]["_id"]),
            "provider": "woocommerce",
            "test_status": "success",
            "tested_at": now_utc().isoformat(),
            "read_endpoint": "products",
            "sample_count": len(body),
            "store_currency": currency,
            "message": summary,
        }
    except APIError as error:
        _mark_test_result(config, False, error.code)
        log_action(user_id, "biashara.woocommerce_connection_tested", "integration_connection", config["connection"]["_id"], {
            "success": False,
            "error_code": error.code,
        })
        raise


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        text = " ".join(str(data or "").split())
        if text:
            self.parts.append(text)


def _plain_text(value, maximum=1000):
    parser = _TextExtractor()
    try:
        parser.feed(str(value or ""))
        parser.close()
    except Exception:
        return ""
    return " ".join(" ".join(parser.parts).split())[:maximum]


def _money_text(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _safe_image_url(product):
    images = product.get("images")
    if not isinstance(images, list):
        return ""
    for item in images[:10]:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("src") or "").strip()
        if len(raw) > 500:
            continue
        parsed = urlparse(raw)
        if parsed.scheme.lower() == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return raw
    return ""


def _source_product(product, config):
    source_id = str(product.get("id") or "").strip()
    if not re.fullmatch(r"[0-9]{1,24}", source_id):
        return None, ["external_id_invalid"]
    product_type = str(product.get("type") or "").strip().lower()
    source_status = str(product.get("status") or "").strip().lower()
    price = _money_text(product.get("price"))
    if price is None:
        price = _money_text(product.get("regular_price"))
    reasons = []
    if product_type != "simple":
        reasons.append("only_simple_products_supported")
    if source_status != "publish":
        reasons.append("product_not_published")
    if price is None:
        reasons.append("price_missing_or_invalid")

    currency = _currency_check(config)
    if not currency["configured"]:
        reasons.append("store_currency_not_confirmed")
    elif not currency["matches_business_currency"]:
        reasons.append("currency_mismatch")

    categories = product.get("categories") if isinstance(product.get("categories"), list) else []
    category = ""
    for item in categories[:20]:
        if isinstance(item, dict) and item.get("name"):
            category = _plain_text(item.get("name"), 120)
            if category:
                break

    stock_quantity = product.get("stock_quantity")
    try:
        stock = Decimal(str(stock_quantity)) if stock_quantity is not None else None
    except (InvalidOperation, TypeError, ValueError):
        stock = None
    if stock is not None and (not stock.is_finite() or stock < 0):
        stock = None

    clean = {
        "external_id": source_id,
        "name": _plain_text(product.get("name"), 160),
        "description": _plain_text(product.get("short_description") or product.get("description"), 1000),
        "description_source_field": "short_description" if _plain_text(product.get("short_description"), 1000) else "description",
        "source_regular_price": _money_text(product.get("regular_price")),
        "source_sale_price": _money_text(product.get("sale_price")),
        "sku": str(product.get("sku") or "").strip()[:80],
        "product_type": product_type,
        "source_status": source_status,
        "price": price,
        "store_currency": currency["store_currency"],
        "currency_matches_business": currency["matches_business_currency"],
        "category": category,
        "image_url": _safe_image_url(product),
        "source_stock_managed": bool(product.get("manage_stock")),
        "source_stock_quantity": float(stock) if stock is not None else None,
        "source_stock_status": str(product.get("stock_status") or "")[:40],
        "source_modified_at": str(product.get("date_modified_gmt") or product.get("date_modified") or "")[:100],
        "import_stock_policy": "not_imported_in_catalogue_import",
        "import_cost_price_policy": "not_available_from_standard_product_resource",
    }
    if not clean["name"]:
        reasons.append("product_name_missing")
    return clean, reasons


def _local_product_snapshot(product):
    return {
        "name": _plain_text(product.get("name"), 160),
        "sku": str(product.get("sku") or "").strip()[:80],
        "price": _money_text(product.get("price")),
        "description": _plain_text(product.get("description"), 1000),
    }


def _source_product_snapshot(clean):
    return {
        "name": clean.get("name", ""),
        "sku": clean.get("sku", ""),
        "price": clean.get("price"),
        "regular_price": clean.get("source_regular_price"),
        "sale_price": clean.get("source_sale_price"),
        "description": clean.get("description", ""),
        "description_source_field": clean.get("description_source_field", "description"),
    }


def _snapshot_fingerprint(snapshot):
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _public_mapping_status(mapping):
    if not mapping:
        return None
    return {
        "status": mapping.get("import_status"),
        "local_product_id": str(mapping.get("local_resource_id") or "") or None,
        "last_synced_at": (
            mapping["last_synced_at"].isoformat()
            if isinstance(mapping.get("last_synced_at"), datetime)
            else mapping.get("last_synced_at")
        ),
    }


def preview_products(user_id, connection_id, page=1, per_page=20):
    config = _load_connection(user_id, connection_id, "integration.view", require_enabled=True)
    try:
        page = int(page)
        per_page = min(max(int(per_page), 1), MAX_PAGE_SIZE)
    except (TypeError, ValueError, OverflowError):
        raise APIError("page and per_page must be integers.", 422, "invalid_pagination")
    if page < 1 or page > 10000:
        raise APIError("page is out of range.", 422, "invalid_pagination")

    body, headers = _api_get(config, "products", {
        "per_page": per_page,
        "page": page,
        "status": "publish",
        "_fields": PRODUCT_FIELDS,
    })
    if not isinstance(body, list):
        raise APIError("WooCommerce products endpoint did not return a list.", 502, "woocommerce_response_invalid")

    mappings = collection(MAPPINGS_COLLECTION)
    products = collection(PRODUCTS_COLLECTION)
    previews = []
    for source in body:
        if not isinstance(source, dict):
            continue
        clean, reasons = _source_product(source, config)
        if clean is None:
            previews.append({"external_id": "", "importable": False, "reasons": reasons})
            continue
        mapping_query = {
            "business_id": config["business_id"],
            "connection_id": str(config["connection"]["_id"]),
            "resource_type": "product",
            "external_id": clean["external_id"],
        }
        mapping = mappings.find_one(mapping_query)
        marker_product = products.find_one({
            "business_id": config["business_id"],
            f"integration_sources.{config['connection']['_id']}.external_id": clean["external_id"],
        })
        if mapping and mapping.get("import_status") == "imported":
            reasons.append("already_imported")
        elif marker_product:
            reasons.append("import_recovery_pending")
        elif clean["sku"]:
            same_sku = products.find_one({
                "business_id": config["business_id"],
                "sku": clean["sku"],
                "status": {"$ne": "deleted"},
            })
            if same_sku:
                reasons.append("local_sku_conflict")

        previews.append({
            **clean,
            "importable": len(reasons) == 0,
            "reasons": reasons,
            "existing_mapping": _public_mapping_status(mapping),
        })

    try:
        total = int(headers.get("X-WP-Total", len(body)) or len(body))
        total_pages = int(headers.get("X-WP-TotalPages", 1) or 1)
    except (ValueError, TypeError):
        total, total_pages = len(body), 1
    return {
        "connection_id": str(config["connection"]["_id"]),
        "provider": "woocommerce",
        "page": page,
        "per_page": per_page,
        "total": max(total, 0),
        "total_pages": max(total_pages, 1),
        "store_currency": _currency_check(config),
        "stock_policy": "Preview shows source stock but never changes Biashara stock.",
        "products": previews,
    }


def _product_import_payload(clean, config, external_id):
    external_sku = str(clean.get("sku") or "").strip()
    sku = external_sku or f"WC-{str(config['connection']['_id'])[-8:]}-{external_id}"
    return {
        "name": clean["name"],
        "description": clean["description"],
        "category": clean["category"],
        "sku": sku[:80],
        "price": clean["price"],
        "cost_price": 0,
        "currency": _currency_check(config)["business_currency"],
        "stock_quantity": 0,
        "low_stock_threshold": 5,
        "unit": "piece",
        "image_url": clean["image_url"],
        "status": "active",
    }


def _source_marker_query(config, external_id):
    connection_id = str(config["connection"]["_id"])
    return {
        "business_id": config["business_id"],
        f"integration_sources.{connection_id}.external_id": str(external_id),
    }


def _mapping_query(config, external_id):
    return {
        "business_id": config["business_id"],
        "connection_id": str(config["connection"]["_id"]),
        "resource_type": "product",
        "external_id": str(external_id),
    }


def _finish_mapping(mapping, config, product, source_version, source_snapshot=None):
    now = now_utc()
    local_snapshot = _local_product_snapshot(product)
    provider_snapshot = _source_product_snapshot(source_snapshot or {})
    values = {
        "business_id": config["business_id"],
        "connection_id": str(config["connection"]["_id"]),
        "provider": "woocommerce",
        "resource_type": "product",
        "external_id": str((mapping or {}).get("external_id") or product.get("integration_sources", {}).get(str(config["connection"]["_id"]), {}).get("external_id") or ""),
        "local_resource_id": str(product.get("_id") or product.get("id") or ""),
        "import_status": "imported",
        "external_version": str(source_version or "")[:100],
        "source_field_snapshot": provider_snapshot,
        "last_synced_local_snapshot": local_snapshot,
        "last_synced_local_fingerprint": _snapshot_fingerprint(local_snapshot),
        "last_synced_at": now,
        "last_seen_at": now,
        "updated_at": now,
        "sync_status": "synced",
        "sync_conflict": None,
        "pending_outbound_payload": None,
        "pending_outbound_local_fingerprint": None,
        "lease_token": None,
        "lease_expires_at": None,
        "last_error_code": None,
    }
    mappings = collection(MAPPINGS_COLLECTION)
    query = _mapping_query(config, values["external_id"])
    if mapping:
        mappings.update_one({"_id": mapping["_id"], **query}, {"$set": values})
        return mappings.find_one(query) or {**mapping, **values}
    document = {"_id": ObjectId(), "created_at": now, **values}
    try:
        mappings.insert_one(document)
        return document
    except DuplicateKeyError:
        prior = mappings.find_one(query)
        if prior and prior.get("local_resource_id") == values["local_resource_id"]:
            mappings.update_one({"_id": prior["_id"], **query}, {"$set": values})
            return mappings.find_one(query) or {**prior, **values}
        raise APIError("External product mapping conflicts with an existing import.", 409, "external_mapping_conflict")


def _claim_mapping(config, external_id):
    mappings = collection(MAPPINGS_COLLECTION)
    query = _mapping_query(config, external_id)
    existing = mappings.find_one(query)
    now = now_utc()
    token = secrets.token_urlsafe(18)
    lease_expiry = now + timedelta(seconds=IMPORT_LEASE_SECONDS)
    if existing and existing.get("import_status") == "imported":
        return {"state": "imported", "mapping": existing, "token": None}

    if existing:
        expiry = existing.get("lease_expires_at")
        if existing.get("import_status") == "importing" and isinstance(expiry, datetime) and expiry > now:
            return {"state": "in_progress", "mapping": existing, "token": None}
        update = mappings.find_one_and_update(
            {
                "_id": existing["_id"],
                **query,
                "import_status": existing.get("import_status"),
                "lease_token": existing.get("lease_token"),
            },
            {"$set": {
                "import_status": "importing",
                "lease_token": token,
                "lease_expires_at": lease_expiry,
                "last_error_code": None,
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not update:
            return {"state": "in_progress", "mapping": existing, "token": None}
        return {"state": "claimed", "mapping": update, "token": token}

    document = {
        "_id": ObjectId(),
        **query,
        "provider": "woocommerce",
        "local_resource_id": None,
        "import_status": "importing",
        "external_version": "",
        "lease_token": token,
        "lease_expires_at": lease_expiry,
        "last_error_code": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        mappings.insert_one(document)
        return {"state": "claimed", "mapping": document, "token": token}
    except DuplicateKeyError:
        prior = mappings.find_one(query)
        if prior:
            return {"state": "in_progress", "mapping": prior, "token": None}
        raise


def _mark_import_failed(config, external_id, token, error_code):
    collection(MAPPINGS_COLLECTION).update_one(
        {
            **_mapping_query(config, external_id),
            "import_status": "importing",
            "lease_token": token,
        },
        {"$set": {
            "import_status": "failed",
            "lease_token": None,
            "lease_expires_at": None,
            "last_error_code": str(error_code or "product_import_failed")[:100],
            "updated_at": now_utc(),
        }},
    )


def import_products(user_id, connection_id, external_product_ids):
    config = _load_connection(user_id, connection_id, "integration.manage", require_enabled=True)
    # Import needs both integration administration and catalogue management.
    # Fail before making remote calls or claiming import leases if either role
    # permission is absent.
    require_permission(user_id, "products.manage", business_id=config["business_id"])
    currency = _currency_check(config)
    if not currency["configured"]:
        raise APIError(
            "Confirm the WooCommerce store_currency in connection metadata before importing prices.",
            409,
            "woocommerce_store_currency_not_confirmed",
        )
    if not currency["matches_business_currency"]:
        raise APIError(
            "WooCommerce store currency does not match the selected business currency. Import is blocked to prevent incorrect prices.",
            409,
            "woocommerce_currency_mismatch",
        )
    if not isinstance(external_product_ids, list) or not external_product_ids or len(external_product_ids) > MAX_IMPORT_BATCH:
        raise APIError("external_product_ids must contain 1–50 product IDs.", 422, "invalid_import_batch")

    ids = []
    for raw in external_product_ids:
        value = str(raw or "").strip()
        if not re.fullmatch(r"[0-9]{1,24}", value):
            raise APIError("Every external product ID must be a positive numeric WooCommerce ID.", 422, "invalid_external_product_id")
        if value not in ids:
            ids.append(value)

    body, _headers = _api_get(config, "products", {
        "include": ",".join(ids),
        "per_page": min(len(ids), MAX_PAGE_SIZE),
        "page": 1,
        "status": "publish",
        "_fields": PRODUCT_FIELDS,
    })
    if not isinstance(body, list):
        raise APIError("WooCommerce product endpoint did not return a list.", 502, "woocommerce_response_invalid")
    source_by_id = {
        str(row.get("id")): row
        for row in body
        if isinstance(row, dict) and re.fullmatch(r"[0-9]{1,24}", str(row.get("id") or ""))
    }

    report = {
        "connection_id": str(config["connection"]["_id"]),
        "provider": "woocommerce",
        "requested": len(ids),
        "imported": 0,
        "already_imported": 0,
        "in_progress": 0,
        "skipped": 0,
        "failed": 0,
        "results": [],
        "stock_policy": "Source stock was not imported or modified. Reconcile inventory separately before enabling stock sync.",
        "cost_price_policy": "Standard WooCommerce product resources do not provide a verified cost price; Biashara cost price remains zero until entered by the merchant.",
    }

    mappings = collection(MAPPINGS_COLLECTION)
    products = collection(PRODUCTS_COLLECTION)
    for external_id in ids:
        source = source_by_id.get(external_id)
        if not source:
            report["skipped"] += 1
            report["results"].append({"external_id": external_id, "status": "skipped", "reason": "not_found_or_not_published"})
            continue

        clean, reasons = _source_product(source, config)
        if clean is None or reasons:
            report["skipped"] += 1
            report["results"].append({"external_id": external_id, "status": "skipped", "reason": reasons or ["product_not_importable"]})
            continue

        query = _mapping_query(config, external_id)
        mapping = mappings.find_one(query)
        existing_marker_product = products.find_one(_source_marker_query(config, external_id))
        if existing_marker_product:
            _finish_mapping(mapping, config, existing_marker_product, clean["source_modified_at"], source_snapshot=clean)
            report["already_imported"] += 1
            report["results"].append({
                "external_id": external_id,
                "status": "already_imported",
                "local_product_id": str(existing_marker_product.get("_id")),
                "recovered_mapping": not bool(mapping and mapping.get("import_status") == "imported"),
            })
            continue
        if mapping and mapping.get("import_status") == "imported":
            local_id = str(mapping.get("local_resource_id") or "")
            report["failed"] += 1
            report["results"].append({
                "external_id": external_id,
                "status": "failed",
                "reason": "mapped_local_product_missing",
                "local_product_id": local_id or None,
            })
            continue

        payload = _product_import_payload(clean, config, external_id)
        if clean.get("sku"):
            collision = products.find_one({
                "business_id": config["business_id"],
                "sku": clean["sku"],
                "status": {"$ne": "deleted"},
            })
            if collision:
                report["skipped"] += 1
                report["results"].append({
                    "external_id": external_id,
                    "status": "skipped",
                    "reason": "local_sku_conflict",
                    "local_product_id": str(collision.get("_id") or ""),
                })
                continue
        else:
            # Generated SKUs are deterministic and collision-checked too.
            collision = products.find_one({
                "business_id": config["business_id"],
                "sku": payload["sku"],
                "status": {"$ne": "deleted"},
            })
            if collision:
                report["skipped"] += 1
                report["results"].append({
                    "external_id": external_id,
                    "status": "skipped",
                    "reason": "generated_sku_conflict",
                    "local_product_id": str(collision.get("_id") or ""),
                })
                continue

        claim = _claim_mapping(config, external_id)
        if claim["state"] == "imported":
            report["already_imported"] += 1
            report["results"].append({"external_id": external_id, "status": "already_imported"})
            continue
        if claim["state"] == "in_progress":
            # Before reporting in progress, check once more for a product marker
            # in case a previous process died between product insert and mapping ack.
            recovered = products.find_one(_source_marker_query(config, external_id))
            if recovered:
                _finish_mapping(claim["mapping"], config, recovered, clean["source_modified_at"], source_snapshot=clean)
                report["already_imported"] += 1
                report["results"].append({
                    "external_id": external_id,
                    "status": "already_imported",
                    "local_product_id": str(recovered.get("_id") or ""),
                    "recovered_mapping": True,
                })
            else:
                report["in_progress"] += 1
                report["results"].append({"external_id": external_id, "status": "in_progress", "reason": "another import holds the lease"})
            continue

        token = claim["token"]
        try:
            product = biashara_services.create_product(
                user_id,
                payload,
                _integration_source={
                    "provider": "woocommerce",
                    "connection_id": str(config["connection"]["_id"]),
                    "external_id": external_id,
                    "source_version": clean["source_modified_at"],
                },
            )
            product_id = str(product.get("id") or "")
            saved_mapping = mappings.find_one(query) or claim["mapping"]
            _finish_mapping(saved_mapping, config, product, clean["source_modified_at"], source_snapshot=clean)
            report["imported"] += 1
            report["results"].append({
                "external_id": external_id,
                "status": "imported",
                "local_product_id": product_id,
                "product_name": clean["name"],
                "price": clean["price"],
                "currency": currency["business_currency"],
                "stock_quantity": 0,
            })
        except Exception as error:
            error_code = error.code if isinstance(error, APIError) else "product_import_failed"
            _mark_import_failed(config, external_id, token, error_code)
            logger.warning(
                "WooCommerce product import failed (external_id_hash=%s, error=%s)",
                __import__("hashlib").sha256(external_id.encode("utf-8")).hexdigest()[:12],
                type(error).__name__,
            )
            report["failed"] += 1
            report["results"].append({
                "external_id": external_id,
                "status": "failed",
                "reason": error_code,
            })

    log_action(user_id, "biashara.woocommerce_products_imported", "integration_connection", config["connection"]["_id"], {
        "requested": len(ids),
        "imported": report["imported"],
        "skipped": report["skipped"],
        "failed": report["failed"],
    })
    return report
