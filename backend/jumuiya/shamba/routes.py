from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user_id,
)

from backend.jumuiya.core.responses import (
    ok,
    created,
)

from backend.jumuiya.core.errors import APIError

from backend.jumuiya.shamba import schemas, services


shamba_bp = Blueprint(
    "jumuiya_shamba",
    __name__,
)


# =========================================================
# HELPERS
# =========================================================

def body():
    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def validate(fn, data):
    try:
        return fn(data)

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


# =========================================================
# HEALTH
# =========================================================

@shamba_bp.get("/health")
def health():
    return ok({
        "hub": "shamba",
        "status": "online",
    })


# =========================================================
# FARMER PROFILE
# =========================================================

@shamba_bp.get("/farmer")
@require_authenticated
def get_farmer():
    return ok(
        services.get_farmer(
            current_user_id()
        )
    )


@shamba_bp.post("/farmer")
@require_authenticated
def save_farmer():
    payload = validate(
        schemas.farmer_payload,
        body(),
    )

    return ok(
        services.create_or_update_farmer(
            current_user_id(),
            payload,
        ),
        "Farmer profile saved.",
    )


# =========================================================
# FARMS
# =========================================================

@shamba_bp.get("/farms")
@require_authenticated
def get_farms():
    return ok(
        services.list_farms(
            current_user_id()
        )
    )


@shamba_bp.post("/farms")
@require_authenticated
def add_farm():
    payload = validate(
        schemas.farm_payload,
        body(),
    )

    return created(
        services.create_farm(
            current_user_id(),
            payload,
        ),
        "Farm created.",
    )


@shamba_bp.get("/farms/<farm_id>")
@require_authenticated
def get_farm(farm_id):
    return ok(
        services.get_farm(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.put("/farms/<farm_id>")
@require_authenticated
def edit_farm(farm_id):
    payload = validate(
        schemas.farm_payload,
        body(),
    )

    return ok(
        services.update_farm(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Farm updated.",
    )


@shamba_bp.delete("/farms/<farm_id>")
@require_authenticated
def remove_farm(farm_id):
    return ok(
        services.delete_farm(
            current_user_id(),
            farm_id,
        ),
        "Farm removed.",
    )


# =========================================================
# CROPS
# =========================================================

@shamba_bp.get("/farms/<farm_id>/crops")
@require_authenticated
def get_crops(farm_id):
    return ok(
        services.list_crops(
            current_user_id(),
            farm_id,
            request.args.get("status"),
        )
    )


@shamba_bp.post("/farms/<farm_id>/crops")
@require_authenticated
def add_crop(farm_id):
    payload = validate(
        schemas.crop_payload,
        body(),
    )

    return created(
        services.create_crop(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Crop added.",
    )


# =========================================================
# FARM ACTIVITIES
# =========================================================

@shamba_bp.get("/farms/<farm_id>/activities")
@require_authenticated
def get_activities(farm_id):
    return ok(
        services.list_activities(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post("/farms/<farm_id>/activities")
@require_authenticated
def add_activity(farm_id):
    payload = validate(
        schemas.activity_payload,
        body(),
    )

    return created(
        services.create_activity(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Farm activity recorded.",
    )


# =========================================================
# HARVESTS
# =========================================================

@shamba_bp.get("/farms/<farm_id>/harvests")
@require_authenticated
def get_harvests(farm_id):
    return ok(
        services.list_harvests(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post("/farms/<farm_id>/harvests")
@require_authenticated
def add_harvest(farm_id):
    payload = validate(
        schemas.harvest_payload,
        body(),
    )

    return created(
        services.create_harvest(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Harvest recorded.",
    )


# =========================================================
# DASHBOARD
# =========================================================

@shamba_bp.get("/dashboard")
@require_authenticated
def get_dashboard():
    return ok(
        services.dashboard(
            current_user_id()
        )
    )
