# backend/jumuiya/elimu/timetable/routes.py

from __future__ import annotations

from functools import wraps

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
)
from backend.jumuiya.core.responses import (
    created,
    ok,
)

from . import schemas, services


# =========================================================
# BLUEPRINT
# =========================================================


timetable_bp = Blueprint(
    "jumuiya_elimu_timetable",
    __name__,
    url_prefix="/timetable",
)


# =========================================================
# REQUEST HELPERS
# =========================================================


def body() -> dict:
    """
    Read and validate the incoming JSON request body.

    Timetable creation/edit requests must be JSON objects. Endpoints
    that do not require a body do not call this helper.
    """
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return payload



def val(
    validator,
    payload: dict,
):
    """
    Run a schema validator and convert ValueError into the project's
    standard validation error.

    APIError is allowed through unchanged so validators can deliberately
    raise project-specific API errors in the future.
    """
    try:
        return validator(payload)
    except APIError:
        raise
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )



def user_id() -> str:
    """
    Resolve the authenticated RevelaCode/Jumuiya user.

    Authentication is enforced by the route decorator. School membership,
    role, permission and resource-scope checks remain in services.py.
    """
    return current_user_id()



def authenticated(fn):
    """
    Explicit authentication boundary for all timetable API endpoints.

    Keeping this at the timetable blueprint makes the module safe when it
    is registered independently from the larger Elimu blueprint.
    """
    @wraps(fn)
    @require_authenticated
    def wrapped(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapped


# =========================================================
# TIMETABLE COLLECTION
# =========================================================


@timetable_bp.get("")
@authenticated
def list_all():
    """
    List timetables available to the authenticated user.
    """
    return ok(
        services.list_timetables(
            user_id()
        )
    )


@timetable_bp.post("")
@authenticated
def create():
    """
    Create a timetable draft.

    The schema accepts only client-owned timetable configuration fields;
    school ownership and created_by are derived by the service layer.
    """
    payload = val(
        schemas.create_payload,
        body(),
    )

    timetable = services.create(
        user_id(),
        payload,
    )

    return created(
        timetable,
        "Timetable draft created.",
    )


# =========================================================
# SINGLE TIMETABLE
# =========================================================


@timetable_bp.get("/<timetable_id>")
@authenticated
def get_one(
    timetable_id: str,
):
    """
    Retrieve one timetable and its entries.
    """
    return ok(
        services.get(
            user_id(),
            timetable_id,
        )
    )


# =========================================================
# DETERMINISTIC GENERATION
# =========================================================


@timetable_bp.post("/<timetable_id>/generate")
@authenticated
def generate(
    timetable_id: str,
):
    """
    Generate a timetable using the deterministic scheduling engine.

    Generator authority, school membership, role permissions, timetable
    ownership/scope and publish-state rules remain in services.py.
    """
    result = services.generate_for(
        user_id(),
        timetable_id,
    )

    return ok(
        result,
        "Timetable generated.",
    )


# =========================================================
# REVELAAI OPTIMIZATION
# =========================================================


@timetable_bp.post("/<timetable_id>/optimize")
@authenticated
def optimize(
    timetable_id: str,
):
    """
    Ask RevelaAI to improve an existing valid timetable.

    RevelaAI remains advisory. The optimizer validates and scores its
    proposal before the service layer can persist an accepted candidate.
    """
    result = services.ai_optimize(
        user_id(),
        timetable_id,
    )

    return ok(
        result,
        "Timetable optimization completed.",
    )


# =========================================================
# ENTRY MANAGEMENT
# =========================================================


@timetable_bp.patch("/entries/<entry_id>")
@authenticated
def edit_entry(
    entry_id: str,
):
    """
    Update one timetable entry.

    The schema limits the editable request fields. The service layer
    verifies the parent timetable, editability state, slot validity and
    full timetable validity before persistence.
    """
    payload = val(
        schemas.patch_entry_payload,
        body(),
    )

    result = services.update_entry(
        user_id(),
        entry_id,
        payload,
    )

    return ok(
        result,
        "Timetable entry updated.",
    )


# =========================================================
# PUBLICATION
# =========================================================


@timetable_bp.post("/<timetable_id>/publish")
@authenticated
def publish(
    timetable_id: str,
):
    """
    Validate and publish a timetable.

    Publishing authorization, non-empty schedule checks, full validation
    and publication metadata are enforced by services.publish().
    """
    result = services.publish(
        user_id(),
        timetable_id,
    )

    return ok(
        result,
        "Timetable published.",
    )


# =========================================================
# TEACHER VIEW
# =========================================================


@timetable_bp.get("/teacher/me")
@authenticated
def teacher_view():
    """
    Return timetable entries relevant to the authenticated teacher.

    The service layer applies the teacher's actual school membership and
    assignment scope. The client cannot supply another teacher id here.
    """
    return ok(
        services.view_for_teacher(
            user_id()
        )
    )


# =========================================================
# CLASS VIEW
# =========================================================


@timetable_bp.get("/class/<class_id>")
@authenticated
def class_view(
    class_id: str,
):
    """
    Return timetable entries for a class.

    Service authorization decides whether the authenticated user may view
    this class. Teachers are therefore prevented from using the route as a
    way to bypass their assigned-class scope.
    """
    return ok(
        services.view_for_class(
            user_id(),
            class_id,
        )
    )
