# backend/jumuiya/community/routes.py

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cloudinary
from cloudinary import uploader
from PIL import Image, UnidentifiedImageError
from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user_id,
)
from backend.jumuiya.core.responses import (
    ok,
    created,
)

from backend.jumuiya.community import (
    discovery,
    schemas,
    services,
)

from backend.jumuiya.community import (
    discovery,
    group_services,
    schemas,
    services,
)


# =========================================================
# BLUEPRINT
# =========================================================

community_bp = Blueprint(
    "jumuiya_community",
    __name__,
)


# =========================================================
# REQUEST HELPERS
# =========================================================

def body():
    """
    Read and validate a JSON request body.

    Community mutation endpoints should never silently accept arbitrary
    request payloads.
    """
    data = request.get_json(
        silent=True,
    )

    if not isinstance(
        data,
        dict,
    ):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def parse_limit(
    default=30,
    maximum=100,
):
    """
    Parse a bounded result limit.

    Existing clients that provide malformed limits retain the old behavior:
    the default is used rather than throwing an unexpected server error.
    """
    raw = request.args.get(
        "limit",
        default,
    )

    try:
        value = int(raw)
    except (
        TypeError,
        ValueError,
    ):
        value = default

    return max(
        1,
        min(
            value,
            maximum,
        ),
    )


def parse_list_arg(
    name: str,
) -> list[str]:
    """
    Parse repeated or comma-separated query parameters.

    Supported:

        ?hub=biashara&hub=shamba

    and:

        ?hubs=biashara,shamba
    """
    values = request.args.getlist(name)

    if not values:
        singular = request.args.get(name)

        if singular:
            values = [singular]

    result: list[str] = []

    for value in values:
        if not isinstance(value, str):
            continue

        for item in value.split(","):
            item = item.strip()

            if item and item not in result:
                result.append(item)

    return result


def candidate_limit_for_discovery(
    limit: int,
) -> int:
    """
    Fetch a larger candidate pool before ranking.

    Ranking works better when Discovery can choose among more candidates than
    the exact number eventually returned to the user.
    """
    return min(
        100,
        max(
            50,
            limit * 4,
        ),
    )


# =========================================================
# COMMUNITY INTELLIGENCE HELPERS
# =========================================================

def feed_candidates(
    user_id,
    *,
    category=None,
    hub=None,
    post_type=None,
    search=None,
    limit=100,
):
    """
    Fetch Community candidates from the existing service layer.

    services.py remains responsible for:
        - MongoDB access
        - publication state
        - existing ownership/source checks
        - author attachment
        - reactions
        - serialization

    discovery.py then decides what deserves attention.
    """
    return services.feed(
        user_id=user_id,
        category=category,
        hub=hub,
        post_type=post_type,
        search=search,
        limit=limit,
    )


def ranked_surface(
    user_id,
    *,
    surface="pulse",
    category=None,
    hub=None,
    post_type=None,
    search=None,
    limit=30,
    mode="relevant",
    intent=None,
):
    """
    Build a smart Community surface from the existing feed candidates.

    For now the candidate source is Community's existing feed/service layer.
    This gives us a safe compatibility bridge.

    Later Discovery can receive candidates from:
        Community
        Biashara
        Shamba
        Elimu
        Marketplace
    directly.
    """
    candidate_pool = candidate_limit_for_discovery(
        limit,
    )

    candidates = feed_candidates(
        user_id,
        category=category,
        hub=hub,
        post_type=post_type,
        search=search,
        limit=candidate_pool,
    )

    user_context = {
        # These fields are intentionally optional.
        #
        # The discovery engine will safely operate with an incomplete
        # context. As richer profile/preferences services are introduced,
        # this context can be populated centrally.
        "active_hubs": [],
        "hubs": [],
        "preferred_hubs": [],
        "interests": [],
        "topics": [],
        "categories": [],
        "blocked_users": [],
        "muted_users": [],
        "hidden_items": [],
        "reported_items": [],
        "viewed_items": [],
        "interacted_items": [],
        "opened_items": [],
        "connected_user_ids": [],
    }

    # -----------------------------------------------------
    # PULSE
    # -----------------------------------------------------

    if surface == "pulse":
        results = discovery.build_pulse(
            candidates,
            user_context=user_context,
            limit=limit,
            mode=mode,
        )

        return results

    # -----------------------------------------------------
    # DISCOVERY
    # -----------------------------------------------------

    if surface == "discovery":
        results = discovery.build_discovery(
            candidates,
            user_context=user_context,
            query=search,
            intent=intent,
            limit=limit,
        )

        return results

    # -----------------------------------------------------
    # NEARBY
    # -----------------------------------------------------

    if surface == "nearby":
        return discovery.nearby(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    # -----------------------------------------------------
    # OPPORTUNITIES
    # -----------------------------------------------------

    if surface == "opportunities":
        return discovery.opportunities(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    # -----------------------------------------------------
    # TRUSTED
    # -----------------------------------------------------

    if surface == "trusted":
        return discovery.trusted(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    # -----------------------------------------------------
    # EXPLORATION
    # -----------------------------------------------------

    if surface == "exploration":
        return discovery.exploration(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    raise APIError(
        "Unsupported Community surface.",
        400,
        "invalid_community_surface",
    )


# =========================================================
# HEALTH
# =========================================================

@community_bp.get("/health")
def health():
    return ok({
        "hub": "community",
        "status": "online",
        "version": "2.0",
        "features": [
            "pulse",
            "discovery",
            "groups",
            "threads",
            "actions",
            "trust",
            "posts",
            "comments",
            "reactions",
            "ecosystem_context",
            "notifications",
        ],
    })


# =========================================================
# SMART PULSE
# =========================================================

@community_bp.get("/pulse")
@require_authenticated
def get_pulse():
    """
    Smart Community Pulse.

    Answers:

        "What is useful to me right now?"

    Supported modes:

        relevant
        recent
        nearby
        actionable
        trusted
        discovery
    """
    user_id = current_user_id()

    limit = parse_limit(
        default=30,
        maximum=50,
    )

    mode = (
        request.args.get(
            "mode",
            "relevant",
        )
        .strip()
        .lower()
    )

    return ok(
        ranked_surface(
            user_id,
            surface="pulse",
            category=request.args.get(
                "category",
            ),
            hub=request.args.get(
                "hub",
            ),
            post_type=request.args.get(
                "type",
            ),
            search=request.args.get(
                "search",
            ),
            limit=limit,
            mode=mode,
        )
    )


# =========================================================
# COMMUNITY MEDIA UPLOAD
# =========================================================

COMMUNITY_MEDIA_COLLECTION = "jumuiya_community_media"
COMMUNITY_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
COMMUNITY_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
COMMUNITY_IMAGE_MAX_BYTES = 12 * 1024 * 1024
COMMUNITY_VIDEO_MAX_BYTES = 50 * 1024 * 1024


def _configure_community_cloudinary():
    cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
    if cloudinary_url:
        cloudinary.config(secure=True)
        return

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
    if not all((cloud_name, api_key, api_secret)):
        raise APIError(
            "Community media storage is not configured. Configure Cloudinary on the backend.",
            503,
            "media_storage_not_configured",
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def _community_media_response(document):
    return {
        "id": str(document["_id"]),
        "url": document.get("secure_url", ""),
        "file_name": document.get("file_name", "media"),
        "kind": document.get("kind", "image"),
        "mime_type": document.get("mime_type", ""),
        "format": document.get("format", ""),
        "size_bytes": int(document.get("size_bytes", 0) or 0),
        "created_at": document.get("created_at").isoformat()
        if isinstance(document.get("created_at"), datetime)
        else None,
    }


@community_bp.post("/media/upload")
@require_authenticated
def upload_community_media():
    """Upload an image/video for an authenticated Community post."""
    user_id = str(current_user_id())
    upload = request.files.get("file")

    if not upload or not upload.filename:
        raise APIError("Choose an image or video to upload.", 400, "media_file_required")

    file_name = Path(upload.filename.replace("\\", "/")).name[:180]
    extension = Path(file_name).suffix.lower()
    if extension in COMMUNITY_IMAGE_EXTENSIONS:
        kind = "image"
        resource_type = "image"
        max_bytes = COMMUNITY_IMAGE_MAX_BYTES
    elif extension in COMMUNITY_VIDEO_EXTENSIONS:
        kind = "video"
        resource_type = "video"
        max_bytes = COMMUNITY_VIDEO_MAX_BYTES
    else:
        raise APIError(
            "Supported files are JPG, PNG, WEBP, GIF, MP4, MOV, M4V and WEBM.",
            422,
            "unsupported_media_type",
        )

    if request.content_length and request.content_length > max_bytes + 1024 * 1024:
        raise APIError("The uploaded file is too large.", 413, "media_file_too_large")

    _configure_community_cloudinary()
    temp_path = None
    cloud_public_id = None
    cloud_resource_type = resource_type

    try:
        with tempfile.NamedTemporaryFile(
            prefix="community-media-",
            suffix=extension,
            delete=False,
        ) as temporary:
            temp_path = temporary.name
            total_bytes = 0
            while True:
                chunk = upload.stream.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise APIError(
                        "The uploaded file exceeds the allowed size.",
                        413,
                        "media_file_too_large",
                    )
                temporary.write(chunk)

        if not total_bytes:
            raise APIError("The uploaded file is empty.", 422, "empty_media_file")

        if kind == "image":
            try:
                with Image.open(temp_path) as image:
                    detected = str(image.format or "").upper()
                    permitted = {
                        "JPEG": {".jpg", ".jpeg"},
                        "PNG": {".png"},
                        "WEBP": {".webp"},
                        "GIF": {".gif"},
                    }
                    if extension not in permitted.get(detected, set()):
                        raise APIError(
                            "Image content does not match its file extension.",
                            422,
                            "invalid_image_format",
                        )
                    image.verify()
            except APIError:
                raise
            except (UnidentifiedImageError, OSError, ValueError):
                raise APIError("The uploaded image is invalid.", 422, "invalid_image_file")

        cloud_result = uploader.upload(
            temp_path,
            resource_type=resource_type,
            folder="revelacode/community",
            public_id=uuid4().hex,
            overwrite=False,
            unique_filename=False,
            use_filename=False,
        )
        secure_url = str(cloud_result.get("secure_url") or "")
        cloud_public_id = cloud_result.get("public_id")
        if not secure_url.startswith("https://") or not cloud_public_id:
            raise APIError(
                "The media provider returned an invalid upload result.",
                502,
                "media_storage_invalid_response",
            )

        document = {
            "uploaded_by_user_id": user_id,
            "file_name": file_name,
            "kind": kind,
            "mime_type": str(upload.mimetype or ""),
            "format": str(cloud_result.get("format") or extension.lstrip(".")),
            "size_bytes": int(cloud_result.get("bytes") or total_bytes),
            "secure_url": secure_url,
            "public_id": cloud_public_id,
            "resource_type": resource_type,
            "created_at": datetime.now(timezone.utc),
        }

        inserted = collection(COMMUNITY_MEDIA_COLLECTION).insert_one(document)
        document["_id"] = inserted.inserted_id

        try:
            log_action(
                user_id,
                "community.media.uploaded",
                "community_media",
                inserted.inserted_id,
                {"kind": kind, "size_bytes": document["size_bytes"]},
            )
        except Exception:
            # Audit failure must not invalidate a successful, already-persisted upload.
            pass

        from backend.jumuiya.core.responses import created
        return created(
            {"attachment": _community_media_response(document)},
            "Community media uploaded.",
        )

    except APIError:
        raise
    except Exception as exc:
        if cloud_public_id:
            try:
                uploader.destroy(
                    cloud_public_id,
                    resource_type=cloud_resource_type,
                    invalidate=True,
                )
            except Exception:
                pass
        raise APIError(
            "Community media upload failed. Check Cloudinary configuration and try again.",
            502,
            "media_upload_failed",
        ) from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


# =========================================================
# COMMUNITY GROUPS
# =========================================================

@community_bp.get("/groups")
@require_authenticated
def get_groups():
    result = group_services.list_groups(
        current_user_id(),
        category=request.args.get("category"),
        search=request.args.get(
            "q",
            request.args.get("search", ""),
        ),
        mine=request.args.get(
            "mine",
            "",
        ).strip().lower() in {
            "1",
            "true",
            "yes",
        },
        limit=parse_limit(
            default=100,
            maximum=100,
        ),
    )

    return ok(result)


@community_bp.post("/groups")
@require_authenticated
def create_group():
    result = group_services.create_group(
        current_user_id(),
        body(),
    )

    return created(
        {"group": result},
        "Community group created.",
    )


@community_bp.get("/groups/<group_id>")
@require_authenticated
def get_group(group_id):
    result = group_services.get_group(
        current_user_id(),
        group_id,
    )

    return ok({
        "group": result,
    })


@community_bp.post("/groups/<group_id>/join")
@require_authenticated
def join_group(group_id):
    result = group_services.join_group(
        current_user_id(),
        group_id,
    )

    return ok(
        {"group": result},
        "You have joined the community group.",
    )


@community_bp.delete("/groups/<group_id>/join")
@require_authenticated
def leave_group(group_id):
    result = group_services.leave_group(
        current_user_id(),
        group_id,
    )

    return ok(
        {"group": result},
        "You have left the community group.",
    )


# =========================================================
# DISCOVERY
# =========================================================

@community_bp.get("/discovery")
@require_authenticated
def get_discovery():
    """
    Discovery answers:

        "Who / what / where can I connect with?"

    Examples:

        /discovery?q=mathematics
        /discovery?q=tomatoes&intent=buy
        /discovery?intent=work
        /discovery?hub=shamba
    """
    user_id = current_user_id()

    query = (
        request.args.get(
            "q",
            "",
        )
        .strip()
    )

    intent = (
        request.args.get(
            "intent",
            "",
        )
        .strip()
        .lower()
        or None
    )

    limit = parse_limit(
        default=20,
        maximum=50,
    )

    hubs = parse_list_arg(
        "hub",
    )

    entity_types = parse_list_arg(
        "type",
    )

    # Current candidate source is Community's existing feed. The filters
    # remain useful now, and the service/discovery layer can later expand
    # Discovery into full cross-hub entities.
    candidates = feed_candidates(
        user_id,
        category=request.args.get(
            "category",
        ),
        hub=hubs[0] if hubs else None,
        post_type=None,
        search=query or None,
        limit=candidate_limit_for_discovery(
            limit,
        ),
    )

    user_context = {
        "active_hubs": [],
        "hubs": hubs,
        "preferred_hubs": hubs,
        "interests": [],
        "topics": [],
        "categories": [],
        "blocked_users": [],
        "muted_users": [],
        "hidden_items": [],
        "reported_items": [],
        "viewed_items": [],
        "interacted_items": [],
        "opened_items": [],
        "connected_user_ids": [],
        "discovery_intent": intent,
    }

    return ok(
        discovery.build_discovery(
            candidates,
            user_context=user_context,
            query=query or None,
            intent=intent,
            entity_types=entity_types or None,
            hubs=hubs or None,
            limit=limit,
        )
    )


# =========================================================
# NEARBY
# =========================================================

@community_bp.get("/nearby")
@require_authenticated
def get_nearby():
    user_id = current_user_id()

    limit = parse_limit(
        default=20,
        maximum=50,
    )

    return ok(
        ranked_surface(
            user_id,
            surface="nearby",
            category=request.args.get(
                "category",
            ),
            hub=request.args.get(
                "hub",
            ),
            post_type=request.args.get(
                "type",
            ),
            search=request.args.get(
                "search",
            ),
            limit=limit,
        )
    )


# =========================================================
# OPPORTUNITIES
# =========================================================

@community_bp.get("/opportunities")
@require_authenticated
def get_opportunities():
    user_id = current_user_id()

    limit = parse_limit(
        default=20,
        maximum=50,
    )

    return ok(
        ranked_surface(
            user_id,
            surface="opportunities",
            category=request.args.get(
                "category",
            ),
            hub=request.args.get(
                "hub",
            ),
            post_type=request.args.get(
                "type",
            ),
            search=request.args.get(
                "search",
            ),
            limit=limit,
        )
    )


# =========================================================
# TRUSTED
# =========================================================

@community_bp.get("/trusted")
@require_authenticated
def get_trusted():
    user_id = current_user_id()

    limit = parse_limit(
        default=20,
        maximum=50,
    )

    return ok(
        ranked_surface(
            user_id,
            surface="trusted",
            category=request.args.get(
                "category",
            ),
            hub=request.args.get(
                "hub",
            ),
            post_type=request.args.get(
                "type",
            ),
            search=request.args.get(
                "search",
            ),
            limit=limit,
        )
    )


# =========================================================
# EXPLORATION
# =========================================================

@community_bp.get("/exploration")
@require_authenticated
def get_exploration():
    user_id = current_user_id()

    limit = parse_limit(
        default=20,
        maximum=50,
    )

    return ok(
        ranked_surface(
            user_id,
            surface="exploration",
            category=request.args.get(
                "category",
            ),
            hub=request.args.get(
                "hub",
            ),
            post_type=request.args.get(
                "type",
            ),
            search=request.args.get(
                "search",
            ),
            limit=limit,
        )
    )


# =========================================================
# LEGACY / COMPATIBLE FEED
# =========================================================

@community_bp.get("/feed")
@require_authenticated
def get_feed():
    """
    Existing frontend-compatible feed endpoint.

    By default it now behaves as the intelligent Pulse.

    Examples:

        /feed
        /feed?mode=recent
        /feed?mode=nearby
        /feed?mode=actionable
        /feed?mode=trusted

    Existing filters remain supported.
    """
    user_id = current_user_id()

    limit = parse_limit(
        default=30,
        maximum=100,
    )

    surface = (
        request.args.get(
            "surface",
            "pulse",
        )
        .strip()
        .lower()
    )

    mode = (
        request.args.get(
            "mode",
            "relevant",
        )
        .strip()
        .lower()
    )

    # Preserve the original feed behavior whenever an explicitly unsupported
    # surface is not requested.
    if surface == "pulse":
        return ok(
            ranked_surface(
                user_id,
                surface="pulse",
                category=request.args.get(
                    "category",
                ),
                hub=request.args.get(
                    "hub",
                ),
                post_type=request.args.get(
                    "type",
                ),
                search=request.args.get(
                    "search",
                ),
                limit=limit,
                mode=mode,
            )
        )

    return ok(
        ranked_surface(
            user_id,
            surface=surface,
            category=request.args.get(
                "category",
            ),
            hub=request.args.get(
                "hub",
            ),
            post_type=request.args.get(
                "type",
            ),
            search=request.args.get(
                "search",
            ),
            limit=limit,
            mode=mode,
        )
    )


# =========================================================
# CREATE POST
# =========================================================

@community_bp.post("/posts")
@require_authenticated
def create_post():
    payload = schemas.create_post_payload(
        body()
    )

    return created(
        services.create_post(
            current_user_id(),
            payload,
        ),
        "Community post published.",
    )


# =========================================================
# UPDATE POST
# =========================================================

@community_bp.put(
    "/posts/<post_id>"
)
@require_authenticated
def edit_post(post_id):
    payload = schemas.update_post_payload(
        body()
    )

    return ok(
        services.update_post(
            current_user_id(),
            post_id,
            payload,
        ),
        "Post updated.",
    )


# =========================================================
# DELETE POST
# =========================================================

@community_bp.delete(
    "/posts/<post_id>"
)
@require_authenticated
def remove_post(post_id):
    return ok(
        services.delete_post(
            current_user_id(),
            post_id,
        ),
        "Post deleted.",
    )


# =========================================================
# COMMENTS
# =========================================================

@community_bp.get(
    "/posts/<post_id>/comments"
)
@require_authenticated
def get_comments(post_id):
    return ok(
        services.comments(
            post_id,
            limit=parse_limit(
                default=100,
                maximum=200,
            ),
        )
    )


@community_bp.post(
    "/posts/<post_id>/comments"
)
@require_authenticated
def add_comment(post_id):
    data = body()

    comment_body = data.get(
        "body",
        "",
    )

    if not isinstance(
        comment_body,
        str,
    ):
        raise APIError(
            "body must be text.",
            422,
            "validation_error",
        )

    comment_body = comment_body.strip()

    if not comment_body:
        raise APIError(
            "Comment cannot be empty.",
            422,
            "validation_error",
        )

    if len(comment_body) > 3000:
        raise APIError(
            "Comment must not exceed 3000 characters.",
            422,
            "validation_error",
        )

    return created(
        services.add_comment(
            current_user_id(),
            post_id,
            comment_body,
        ),
        "Comment added.",
    )


# =========================================================
# REACTION
# =========================================================

@community_bp.post(
    "/posts/<post_id>/react"
)
@require_authenticated
def react(post_id):
    return ok(
        services.react(
            current_user_id(),
            post_id,
        )
    )


# =========================================================
# SEARCH
# =========================================================

@community_bp.get("/search")
@require_authenticated
def search():
    query = (
        request.args.get(
            "q",
            "",
        )
        .strip()
    )

    if not query:
        raise APIError(
            "Search query is required.",
            422,
            "search_query_required",
        )

    limit = parse_limit(
        default=20,
        maximum=50,
    )

    results = services.search(
        current_user_id(),
        query,
        limit=limit,
    )

    # Search remains a direct search operation, but ranking now makes the
    # returned results useful rather than purely chronological.
    user_context = {
        "active_hubs": [],
        "hubs": [],
        "preferred_hubs": [],
        "interests": [],
        "topics": [],
        "categories": [],
        "blocked_users": [],
        "muted_users": [],
        "hidden_items": [],
        "reported_items": [],
        "viewed_items": [],
        "interacted_items": [],
        "opened_items": [],
        "connected_user_ids": [],
    }

    ranked = discovery.rank_candidates(
        results,
        user_context=user_context,
        mode="discovery",
        limit=limit,
        diversify=True,
    )

    return ok(
        ranked
    )