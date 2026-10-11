
# backend/jumuiya/elimu/media/routes.py

from __future__ import annotations

import logging
import os
import re
import tempfile
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cloudinary
from cloudinary import uploader

from bson import ObjectId
from PIL import Image, UnidentifiedImageError
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from flask import Blueprint, request

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
)
from backend.jumuiya.core.responses import (
    created,
    deleted,
    ok,
    updated,
)


logger = logging.getLogger("jumuiya.elimu.media")

SCHOOLS = "jumuiya_schools"
MEDIA = "jumuiya_elimu_media"

media_bp = Blueprint(
    "jumuiya_elimu_media",
    __name__,
    url_prefix="/media",
)

CHUNK_SIZE = 1024 * 1024

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
}

IMAGE_FORMATS = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
    "WEBP": {".webp"},
    "GIF": {".gif"},
}

CATEGORIES = {
    "hero",
    "gallery",
    "facilities",
    "academics",
    "sports",
    "events",
    "principal_message",
    "virtual_tour",
}

IMAGE_MAX_BYTES = 12 * 1024 * 1024
VIDEO_MAX_BYTES = 80 * 1024 * 1024


# =========================================================
# GENERAL HELPERS
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


def _slug(value) -> str:
    value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    value = value.encode(
        "ascii",
        "ignore",
    ).decode("ascii").lower()

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    ).strip("-")


def _school_id(school) -> str:
    value = school.get("_id")

    if value is None:
        value = school.get("school_id")

    if value is None:
        raise APIError(
            "The school record has no usable ID.",
            500,
            "invalid_school_record",
        )

    return str(value)


def _school_slug(school) -> str:
    for field in (
        "public_slug",
        "school_slug",
        "website_slug",
        "slug",
    ):
        value = _slug(school.get(field))

        if value:
            return value

    return (
        _slug(school.get("name"))
        or _slug(school.get("code"))
    )


def _owned_school(user_id):
    """
    Resolve the active school that the authenticated user is
    authorized to manage through Elimu media.

    Authorized roles:
      - Owner of an active school.
      - Principal with an active membership in an active school.

    School identity is resolved exclusively from server-side
    ownership or membership records. Client-supplied school IDs
    never grant access.
    """

    uid = str(user_id or "").strip()

    if not uid:
        raise APIError(
            "Authentication is required to manage school media.",
            401,
            "authentication_required",
        )

    schools = collection(SCHOOLS)

    # ---------------------------------------------------------
    # 1. School owner
    # ---------------------------------------------------------
    school = schools.find_one({
        "owner_user_id": uid,
        "status": "active",
    })

    if school:
        return school

    # ---------------------------------------------------------
    # 2. Active principal membership
    # ---------------------------------------------------------
    members = collection(
        "jumuiya_elimu_school_members"
    )

    memberships = members.find({
        "user_id": uid,
        "status": "active",
    }).limit(20)

    for member in memberships:
        role = str(member.get("role") or "").strip().lower()

        # Only principals receive this additional authorization.
        # Teachers, bursars and registrars do not inherit media
        # management privileges from this helper.
        if role not in {
            "principal",
            "school_principal",
        }:
            continue

        membership_school_id = str(
            member.get("school_id") or ""
        ).strip()

        if not membership_school_id:
            continue

        # Existing Elimu records may identify a school through
        # MongoDB's ObjectId or through its string school_id.
        school_identifiers = [
            {"_id": membership_school_id},
            {"school_id": membership_school_id},
        ]

        if ObjectId.is_valid(membership_school_id):
            school_identifiers.append({
                "_id": ObjectId(membership_school_id)
            })
            school_identifiers.append({
                "school_id": ObjectId(membership_school_id)
            })

        school = schools.find_one({
            "status": "active",
            "$or": school_identifiers,
        })

        if not school:
            continue

        # Ensure the membership references the school actually
        # resolved by the database query.
        resolved_school_id = _school_id(school)

        if resolved_school_id != membership_school_id:
            school_field_id = str(
                school.get("school_id") or ""
            ).strip()

            if school_field_id != membership_school_id:
                continue

        return school

    raise APIError(
        "An active school owner account or an active principal "
        "membership in an active school is required to manage media.",
        403,
        "school_media_permission_denied",
    )


def _configure_cloudinary():
    """
    Accept either CLOUDINARY_URL or the three individual
    Cloudinary environment variables.
    """

    cloudinary_url = os.getenv(
        "CLOUDINARY_URL",
        "",
    ).strip()

    if cloudinary_url:
        cloudinary.config(secure=True)
        return

    cloud_name = os.getenv(
        "CLOUDINARY_CLOUD_NAME",
        "",
    ).strip()

    api_key = os.getenv(
        "CLOUDINARY_API_KEY",
        "",
    ).strip()

    api_secret = os.getenv(
        "CLOUDINARY_API_SECRET",
        "",
    ).strip()

    if not all((cloud_name, api_key, api_secret)):
        raise APIError(
            "Media storage is not configured. Set the Cloudinary "
            "environment variables on the backend.",
            503,
            "media_storage_not_configured",
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def _parse_bool(value, default=False):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    value = str(value).strip().lower()

    if value in {"true", "1", "yes", "on"}:
        return True

    if value in {"false", "0", "no", "off"}:
        return False

    raise APIError(
        "Expected a valid boolean value.",
        422,
        "invalid_boolean",
    )


def _required_text(value, field, maximum):
    if not isinstance(value, str):
        raise APIError(
            f"{field} must be text.",
            422,
            "invalid_media_metadata",
        )

    value = value.strip()

    if not value:
        raise APIError(
            f"{field} is required.",
            422,
            "invalid_media_metadata",
        )

    if len(value) > maximum:
        raise APIError(
            f"{field} must not exceed {maximum} characters.",
            422,
            "invalid_media_metadata",
        )

    return value


def _optional_text(value, field, maximum):
    if value is None:
        return ""

    if not isinstance(value, str):
        raise APIError(
            f"{field} must be text.",
            422,
            "invalid_media_metadata",
        )

    value = value.strip()

    if len(value) > maximum:
        raise APIError(
            f"{field} must not exceed {maximum} characters.",
            422,
            "invalid_media_metadata",
        )

    return value


def _normalize_category(value, default="gallery"):
    category = str(
        value or default
    ).strip().lower()

    if category not in CATEGORIES:
        raise APIError(
            "Unsupported media category.",
            422,
            "invalid_media_category",
        )

    return category


# =========================================================
# UPLOAD VALIDATION
# =========================================================

def _copy_upload_to_temp(upload, suffix, max_bytes):
    """
    Stream the upload to a temporary file rather than
    loading the complete video into application memory.

    The temporary file is removed after the Cloudinary
    upload finishes.
    """

    temp_path = None

    try:
        handle = tempfile.NamedTemporaryFile(
            prefix="elimu-media-",
            suffix=suffix,
            delete=False,
        )

        temp_path = handle.name
        total_bytes = 0

        with handle:
            while True:
                chunk = upload.stream.read(CHUNK_SIZE)

                if not chunk:
                    break

                total_bytes += len(chunk)

                if total_bytes > max_bytes:
                    raise APIError(
                        "The uploaded file exceeds the allowed size.",
                        413,
                        "media_file_too_large",
                    )

                handle.write(chunk)

        if total_bytes == 0:
            raise APIError(
                "The uploaded file is empty.",
                422,
                "empty_media_file",
            )

        return temp_path, total_bytes

    except Exception:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

        raise


def _image_dimensions(path, extension):
    """
    Verify that an image can actually be decoded.
    SVG and unsupported image formats are rejected.
    """

    try:
        with Image.open(path) as image:
            image_format = str(
                image.format or ""
            ).upper()

            width, height = image.size

            allowed_extensions = IMAGE_FORMATS.get(
                image_format,
                set(),
            )

            if extension not in allowed_extensions:
                raise APIError(
                    "The image content does not match its file extension.",
                    422,
                    "invalid_image_format",
                )

            image.verify()

            return width, height, image_format.lower()

    except APIError:
        raise

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        raise APIError(
            "The uploaded file is not a valid supported image.",
            422,
            "invalid_image_file",
        )


def _public_school_by_slug(value):
    """
    Resolve a public URL slug without exposing a school's
    management records to the public.

    Explicit website slugs take precedence. Older records
    may fall back to a slug derived from their name or code.
    """

    requested_slug = _slug(value)

    if not requested_slug:
        raise APIError(
            "A school slug is required.",
            400,
            "school_slug_required",
        )

    schools = collection(SCHOOLS)

    slug_fields = (
        "public_slug",
        "school_slug",
        "website_slug",
        "slug",
    )

    for field in slug_fields:
        school = schools.find_one({
            "status": "active",
            field: requested_slug,
        })

        if school:
            return school

    matches = []

    cursor = schools.find({
        "status": "active",
    }).limit(2000)

    for school in cursor:
        if requested_slug in {
            _slug(school.get("name")),
            _slug(school.get("code")),
        }:
            matches.append(school)

    if len(matches) == 1:
        return matches[0]

    raise APIError(
        "The requested public school was not found.",
        404,
        "public_school_not_found",
    )


def _media_document_id(value):
    if not ObjectId.is_valid(str(value)):
        raise APIError(
            "Invalid media ID.",
            400,
            "invalid_media_id",
        )

    return ObjectId(str(value))


# =========================================================
# SERIALIZATION
# =========================================================

def _serialize_media(document):
    if not document:
        return None

    def iso(value):
        return (
            value.isoformat()
            if isinstance(value, datetime)
            else value
        )

    return {
        "id": str(document["_id"]),
        "school_id": str(document.get("school_id", "")),
        "school_slug": document.get("school_slug", ""),
        "school_name": document.get("school_name", ""),
        "kind": document.get("kind", ""),
        "category": document.get("category", "gallery"),
        "title": document.get("title", ""),
        "caption": document.get("caption", ""),
        "alt_text": document.get("alt_text", ""),
        "url": document.get("secure_url", ""),
        "format": document.get("format", ""),
        "size_bytes": document.get("size_bytes", 0),
        "width": document.get("width"),
        "height": document.get("height"),
        "duration": document.get("duration"),
        "is_published": bool(
            document.get("is_published", False)
        ),
        "sort_order": int(
            document.get("sort_order", 0)
        ),
        "created_at": iso(document.get("created_at")),
        "updated_at": iso(document.get("updated_at")),
    }


# =========================================================
# OWNER: LIST MEDIA
# =========================================================

@media_bp.get("/manage")
@require_authenticated
def list_school_media():
    user_id = current_user_id()
    school = _owned_school(user_id)
    sid = _school_id(school)

    documents = (
        collection(MEDIA)
        .find({"school_id": sid})
        .sort([
            ("sort_order", ASCENDING),
            ("created_at", DESCENDING),
        ])
        .limit(200)
    )

    return ok({
        "school_id": sid,
        "school_slug": _school_slug(school),
        "items": [
            _serialize_media(item)
            for item in documents
        ],
    })


# =========================================================
# OWNER: UPLOAD MEDIA
# =========================================================

@media_bp.post("/upload")
@require_authenticated
def upload_school_media():
    user_id = current_user_id()
    school = _owned_school(user_id)

    upload = request.files.get("file")

    if not upload or not upload.filename:
        raise APIError(
            "Choose an image or video file to upload.",
            400,
            "media_file_required",
        )

    safe_name = Path(
        upload.filename.replace("\\", "/")
    ).name

    extension = Path(
        safe_name
    ).suffix.lower()

    if extension in IMAGE_EXTENSIONS:
        kind = "image"
        resource_type = "image"
        max_bytes = IMAGE_MAX_BYTES

    elif extension in VIDEO_EXTENSIONS:
        kind = "video"
        resource_type = "video"
        max_bytes = VIDEO_MAX_BYTES

    else:
        raise APIError(
            "Supported formats are JPG, PNG, WEBP, GIF, MP4, MOV, M4V and WEBM.",
            422,
            "unsupported_media_type",
        )

    _configure_cloudinary()

    default_title = Path(
        safe_name
    ).stem.replace("_", " ").strip()

    title = _optional_text(
        request.form.get("title", default_title),
        "title",
        120,
    )

    if not title:
        title = "School media"

    caption = _optional_text(
        request.form.get("caption", ""),
        "caption",
        1000,
    )

    alt_text = _optional_text(
        request.form.get("alt_text", ""),
        "alt_text",
        300,
    )

    default_category = (
        "gallery" if kind == "image" else "virtual_tour"
    )

    category = _normalize_category(
        request.form.get("category"),
        default_category,
    )

    is_published = _parse_bool(
        request.form.get("is_published"),
        default=False,
    )

    sid = _school_id(school)
    slug = _school_slug(school)

    temp_path = None
    cloud_result = None

    try:
        temp_path, byte_count = _copy_upload_to_temp(
            upload,
            extension,
            max_bytes,
        )

        dimensions = {
            "width": None,
            "height": None,
            "format": extension.lstrip("."),
        }

        if kind == "image":
            width, height, detected_format = (
                _image_dimensions(
                    temp_path,
                    extension,
                )
            )

            dimensions = {
                "width": width,
                "height": height,
                "format": detected_format,
            }

        cloud_result = uploader.upload(
            temp_path,
            resource_type=resource_type,
            folder=f"revelacode/elimu/schools/{sid}",
            public_id=uuid4().hex,
            overwrite=False,
            unique_filename=False,
            use_filename=False,
        )

        secure_url = cloud_result.get("secure_url")
        public_id = cloud_result.get("public_id")

        if not secure_url or not public_id:
            raise APIError(
                "The media provider returned an incomplete upload result.",
                502,
                "media_storage_invalid_response",
            )

        now = now_utc()

        document = {
            "school_id": sid,
            "school_slug": slug,
            "school_name": str(school.get("name", "")),
            "kind": kind,
            "category": category,
            "title": title,
            "caption": caption,
            "alt_text": alt_text,
            "secure_url": secure_url,
            "public_id": public_id,
            "resource_type": resource_type,
            "format": cloud_result.get(
                "format",
                dimensions["format"],
            ),
            "size_bytes": int(
                cloud_result.get("bytes", byte_count)
            ),
            "width": cloud_result.get(
                "width",
                dimensions["width"],
            ),
            "height": cloud_result.get(
                "height",
                dimensions["height"],
            ),
            "duration": cloud_result.get("duration"),
            "is_published": is_published,
            "sort_order": 0,
            "uploaded_by": str(user_id),
            "created_at": now,
            "updated_at": now,
        }

        try:
            inserted = collection(MEDIA).insert_one(
                document
            )

        except Exception:
            # Avoid leaving a Cloudinary asset behind if the
            # metadata could not be recorded in MongoDB.
            try:
                uploader.destroy(
                    public_id,
                    resource_type=resource_type,
                    invalidate=True,
                )
            except Exception:
                logger.exception(
                    "Cloudinary cleanup failed after metadata insert failure."
                )

            raise APIError(
                "The file was uploaded, but its metadata could not be saved.",
                500,
                "media_metadata_save_failed",
            )

        document["_id"] = inserted.inserted_id

        log_action(
            user_id,
            "elimu.media.uploaded",
            "elimu_media",
            inserted.inserted_id,
            {
                "school_id": sid,
                "kind": kind,
                "category": category,
                "is_published": is_published,
            },
        )

        return created(
            _serialize_media(document),
            "School media uploaded successfully.",
        )

    except APIError:
        raise

    except Exception:
        logger.exception(
            "Elimu media upload failed for school %s.",
            sid,
        )

        raise APIError(
            "Media upload failed. Check the file and storage configuration.",
            502,
            "media_upload_failed",
        )

    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.warning(
                    "Could not remove temporary media file."
                )


# =========================================================
# OWNER: UPDATE MEDIA METADATA / PUBLICATION
# =========================================================

@media_bp.patch("/<media_id>")
@require_authenticated
def update_school_media(media_id):
    user_id = current_user_id()
    school = _owned_school(user_id)
    sid = _school_id(school)

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError(
            "A JSON object is required.",
            400,
            "invalid_json",
        )

    changes = {}

    if "title" in data:
        changes["title"] = _required_text(
            data["title"],
            "title",
            120,
        )

    if "caption" in data:
        changes["caption"] = _optional_text(
            data["caption"],
            "caption",
            1000,
        )

    if "alt_text" in data:
        changes["alt_text"] = _optional_text(
            data["alt_text"],
            "alt_text",
            300,
        )

    if "category" in data:
        changes["category"] = _normalize_category(
            data["category"]
        )

    if "is_published" in data:
        if not isinstance(data["is_published"], bool):
            raise APIError(
                "is_published must be true or false.",
                422,
                "invalid_publication_status",
            )

        changes["is_published"] = data["is_published"]

    if "sort_order" in data:
        value = data["sort_order"]

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 9999
        ):
            raise APIError(
                "sort_order must be a whole number from 0 to 9999.",
                422,
                "invalid_sort_order",
            )

        changes["sort_order"] = value

    if not changes:
        raise APIError(
            "No supported media fields were supplied.",
            422,
            "empty_media_update",
        )

    changes["updated_at"] = now_utc()

    media_object_id = _media_document_id(media_id)

    document = collection(MEDIA).find_one_and_update(
        {
            "_id": media_object_id,
            "school_id": sid,
        },
        {
            "$set": changes,
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        raise APIError(
            "Media not found for this school.",
            404,
            "media_not_found",
        )

    log_action(
        user_id,
        "elimu.media.updated",
        "elimu_media",
        media_object_id,
        {
            "school_id": sid,
            "fields": sorted(changes.keys()),
        },
    )

    return updated(
        _serialize_media(document),
        "School media updated successfully.",
    )


# =========================================================
# OWNER: DELETE MEDIA
# =========================================================

@media_bp.delete("/<media_id>")
@require_authenticated
def delete_school_media(media_id):
    user_id = current_user_id()
    school = _owned_school(user_id)
    sid = _school_id(school)

    media_object_id = _media_document_id(media_id)

    document = collection(MEDIA).find_one({
        "_id": media_object_id,
        "school_id": sid,
    })

    if not document:
        raise APIError(
            "Media not found for this school.",
            404,
            "media_not_found",
        )

    _configure_cloudinary()

    try:
        result = uploader.destroy(
            document["public_id"],
            resource_type=document.get(
                "resource_type",
                "image",
            ),
            invalidate=True,
        )

        if result.get("result") not in {"ok", "not found"}:
            raise APIError(
                "The media provider could not delete the file.",
                502,
                "media_storage_delete_failed",
            )

    except APIError:
        raise

    except Exception:
        logger.exception(
            "Cloudinary deletion failed for media %s.",
            media_id,
        )

        raise APIError(
            "The file could not be deleted from media storage.",
            502,
            "media_storage_delete_failed",
        )

    collection(MEDIA).delete_one({
        "_id": media_object_id,
        "school_id": sid,
    })

    log_action(
        user_id,
        "elimu.media.deleted",
        "elimu_media",
        media_object_id,
        {
            "school_id": sid,
            "kind": document.get("kind"),
        },
    )

    return deleted(
        {"id": str(media_object_id)},
        "School media deleted successfully.",
    )


# =========================================================
# PUBLIC: SCHOOL GALLERY / VIDEOS
# =========================================================

@media_bp.get("/public/<slug>")
def get_public_school_media(slug):
    school = _public_school_by_slug(slug)
    sid = _school_id(school)

    query = {
        "school_id": sid,
        "is_published": True,
    }

    kind = request.args.get("kind", "").strip().lower()
    category = request.args.get(
        "category",
        "",
    ).strip().lower()

    if kind:
        if kind not in {"image", "video"}:
            raise APIError(
                "kind must be image or video.",
                400,
                "invalid_media_kind",
            )

        query["kind"] = kind

    if category:
        if category not in CATEGORIES:
            raise APIError(
                "Unsupported media category.",
                400,
                "invalid_media_category",
            )

        query["category"] = category

    documents = (
        collection(MEDIA)
        .find(query)
        .sort([
            ("sort_order", ASCENDING),
            ("created_at", DESCENDING),
        ])
        .limit(100)
    )

    return ok({
        "school": {
            "id": sid,
            "name": str(school.get("name", "")),
            "slug": _school_slug(school),
        },
        "items": [
            _serialize_media(item)
            for item in documents
        ],
    })