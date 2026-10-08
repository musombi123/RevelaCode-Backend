# backend/jumuiya/elimu/sync/routes.py
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id
from backend.jumuiya.core.responses import ok, created

from . import schemas, services


# ============================================================
# BLUEPRINT
# ============================================================

sync_bp = Blueprint(
    "jumuiya_elimu_sync",
    __name__,
    url_prefix="/sync",
)


# ============================================================
# REQUEST HELPERS
# ============================================================

def body() -> dict:
    """
    Require a JSON object request body.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def optional_body() -> dict:
    """
    Accept an empty body for lifecycle/control endpoints while still
    rejecting malformed non-object JSON.
    """
    if not request.data:
        return {}

    data = request.get_json(silent=True)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body must be an object.",
            400,
            "invalid_json",
        )

    return data


def val(fn, data):
    """
    Run a schema validator and convert ValueError into APIError.
    """
    try:
        return fn(data)
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


def query_dict() -> dict:
    """
    Convert query-string parameters into a normal dictionary.

    Flask's request.args may contain MultiDict values; for the sync
    endpoints we intentionally use the final scalar value.
    """
    return {
        str(key): request.args.get(key)
        for key in request.args.keys()
    }


# ============================================================
# CONNECTIONS
# ============================================================

@sync_bp.get("/connections")
def connections():
    return ok(
        services.list_connections(
            current_user_id()
        )
    )


@sync_bp.post("/connections")
def create_connection():
    payload = val(
        schemas.connection_payload,
        body(),
    )

    return created(
        services.create_connection(
            current_user_id(),
            payload,
        ),
        "Desktop sync connection created.",
    )


@sync_bp.get("/connections/<connection_id>")
def get_connection(connection_id):
    return ok(
        services.get_connection(
            current_user_id(),
            connection_id,
        )
    )


@sync_bp.post("/connections/<connection_id>/activate")
def activate_connection(connection_id):
    return ok(
        services.activate_connection(
            current_user_id(),
            connection_id,
        ),
        "Sync connection activated.",
    )


@sync_bp.post("/connections/<connection_id>/pause")
def pause_connection(connection_id):
    return ok(
        services.pause_connection(
            current_user_id(),
            connection_id,
        ),
        "Sync connection paused.",
    )


@sync_bp.post("/connections/<connection_id>/revoke")
def revoke_connection(connection_id):
    return ok(
        services.revoke_connection(
            current_user_id(),
            connection_id,
        ),
        "Sync connection revoked.",
    )


@sync_bp.post("/connections/<connection_id>/heartbeat")
def connection_heartbeat(connection_id):
    payload = optional_body()

    return ok(
        services.heartbeat(
            current_user_id(),
            connection_id,
            payload,
        ),
        "Sync connection heartbeat received.",
    )


# ============================================================
# DEVICES
# ============================================================

@sync_bp.get("/devices")
def devices():
    return ok(
        services.list_devices(
            current_user_id()
        )
    )


@sync_bp.post("/devices")
def register_device():
    payload = val(
        schemas.device_payload,
        body(),
    )

    return created(
        services.register_device(
            current_user_id(),
            payload,
        ),
        "Sync device registered.",
    )


# ============================================================
# INGEST / PUSH
# ============================================================

@sync_bp.post("/ingest")
def ingest():
    payload = val(
        schemas.records_payload,
        body(),
    )

    return ok(
        services.ingest(
            current_user_id(),
            payload,
        )
    )


# ============================================================
# CONFLICTS
# ============================================================

@sync_bp.get("/conflicts")
def conflicts():
    status = request.args.get(
        "status",
        "open",
    )

    return ok(
        services.conflicts(
            current_user_id(),
            status,
        )
    )


@sync_bp.post("/conflicts/<conflict_id>/resolve")
def resolve_conflict(conflict_id):
    payload = val(
        schemas.conflict_resolution_payload,
        body(),
    )

    return ok(
        services.resolve_conflict(
            current_user_id(),
            conflict_id,
            payload,
        ),
        "Sync conflict resolved.",
    )


# ============================================================
# JOBS
# ============================================================

@sync_bp.get("/jobs")
def jobs():
    filters = val(
        schemas.job_query_params,
        query_dict(),
    )

    return ok(
        services.list_jobs(
            current_user_id(),
            filters,
        )
    )


@sync_bp.get("/jobs/<job_id>")
def get_job(job_id):
    return ok(
        services.get_job(
            current_user_id(),
            job_id,
        )
    )


@sync_bp.post("/jobs/<job_id>/pause")
def pause_job(job_id):
    return ok(
        services.pause_job(
            current_user_id(),
            job_id,
        ),
        "Sync job paused.",
    )


@sync_bp.post("/jobs/<job_id>/resume")
def resume_job(job_id):
    return ok(
        services.resume_job(
            current_user_id(),
            job_id,
        ),
        "Sync job resumed.",
    )


@sync_bp.post("/jobs/<job_id>/cancel")
def cancel_job(job_id):
    return ok(
        services.cancel_job(
            current_user_id(),
            job_id,
        ),
        "Sync job cancelled.",
    )


@sync_bp.post("/jobs/<job_id>/retry")
def retry_job(job_id):
    payload = val(
        schemas.job_control_payload,
        optional_body(),
    )

    return ok(
        services.retry_job(
            current_user_id(),
            job_id,
            payload,
        ),
        "Sync job queued for retry.",
    )


@sync_bp.post("/jobs/recover")
def recover_jobs():
    return ok(
        services.recover_jobs(
            current_user_id()
        ),
        "Stale sync jobs recovered.",
    )


# ============================================================
# STATUS / MONITORING
# ============================================================

@sync_bp.get("/status")
def sync_status():
    return ok(
        services.sync_status(
            current_user_id()
        )
    )


# ============================================================
# EXPORT
# ============================================================

@sync_bp.get("/export/<entity_type>")
def export_entity(entity_type):
    """
    Backward-compatible JSON export endpoint.

    The exporter service can later be exposed through dedicated
    downloadable CSV/XLSX routes without changing this contract.
    """
    return ok(
        {
            "entity_type": entity_type,
            "records": services.export_records(
                current_user_id(),
                entity_type,
            ),
        }
    )