# backend/jumuiya/elimu/sync/bulk_import.py
from __future__ import annotations

"""Safe staged migration imports into the existing Elimu Sync engine.

Uploads are parsed and previewed without touching authoritative school data.
Starting an import requires a designated Principal account or a valid pending
Principal invitation. Records are then reconciled in small, audited batches by
the existing Sync engine; the import never hard-deletes existing records.
"""

import hashlib
import io
import json
import re
import secrets
import zipfile
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping

from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize

from ..staff.models import (
    COLLECTION as STAFF_COLLECTION,
    INVITATIONS as STAFF_INVITATIONS,
    invitation_is_usable,
)
from . import importer, services
from .mapper import canonical_entity_type


IMPORTS = "jumuiya_elimu_sync_imports"
IMPORT_BATCHES = "jumuiya_elimu_sync_import_batches"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ZIP_UNPACKED_BYTES = 80 * 1024 * 1024
MAX_ZIP_FILES = 100
MAX_IMPORT_ROWS = 50000
MAX_RECORD_BYTES = 700 * 1024
MAX_BATCH_BYTES = 900 * 1024
MAX_BATCH_RECORDS = 100
IMPORT_TTL = timedelta(hours=4)

# Account, school-ownership and staff relationships are intentionally excluded.
# They must be established with Elimu's authenticated invitation/membership flow.
IMPORTABLE_ENTITIES = {
    "classes",
    "students",
    "lessons",
    "assignments",
    "attendance",
    "assessments",
    "fees",
    "cbc_projects",
    "events",
    "timetables",
    "timetable_entries",
}
ENTITY_ORDER = (
    "classes",
    "students",
    "lessons",
    "assignments",
    "attendance",
    "assessments",
    "fees",
    "cbc_projects",
    "events",
    "timetables",
    "timetable_entries",
)
EXTRA_ENTITY_ALIASES = {
    "pupil": "students",
    "pupils": "students",
    "learner": "students",
    "learners": "students",
    "student_list": "students",
    "student_records": "students",
    "class_list": "classes",
    "class_records": "classes",
    "fee_ledger": "fees",
    "fee_ledgers": "fees",
    "payments": "fees",
    "student_payments": "fees",
    "attendance_records": "attendance",
    "exam_results": "assessments",
    "marks": "assessments",
    "school_events": "events",
    "event_calendar": "events",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _school_id(member: Mapping[str, Any]) -> str:
    value = _text(member.get("school_id"))
    if not value:
        raise APIError("An active Elimu school is required for imports.", 403, "school_required")
    return value


def _authorize_school(user_id: Any) -> str:
    member = authorize(user_id, "sync.import")
    return _school_id(member)


def _canonical_filename_entity(filename: str) -> str | None:
    stem = PurePosixPath(str(filename or "")).stem.casefold()
    stem = re.sub(r"[\s.-]+", "_", stem).strip("_")
    stem = re.sub(r"^(tbl|table|legacy|export|data)_?", "", stem)
    stem = re.sub(r"_?(export|data|records|backup|dump)$", "", stem)
    if stem in EXTRA_ENTITY_ALIASES:
        stem = EXTRA_ENTITY_ALIASES[stem]
    try:
        return canonical_entity_type(stem)
    except (ValueError, TypeError):
        return None


def _json_load(data: bytes, filename: str) -> Any:
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError(f"{filename}: invalid JSON ({exc}).", 422, "invalid_import_json") from exc


def _migration_entities(document: Any) -> tuple[dict[str, list], list[str]] | None:
    """Recognize a multi-entity migration JSON envelope or an object of arrays."""
    if not isinstance(document, Mapping):
        return None
    schema = _text(document.get("schema")).casefold()
    raw_entities = document.get("entities")
    if schema == "revelacode-elimu-migration-v1" and not isinstance(raw_entities, Mapping):
        raise APIError("Migration envelope must contain an 'entities' object.", 422, "invalid_migration_envelope")
    if isinstance(raw_entities, Mapping):
        source = raw_entities
    elif not _text(document.get("entity_type")) and isinstance(document.get("records"), list):
        return None
    elif not _text(document.get("entity_type")):
        # Legacy JSON dumps commonly contain {students: [...], classes: [...]}.
        source = {key: value for key, value in document.items() if isinstance(value, list)}
        known_arrays = [key for key in source if _canonical_filename_entity(str(key))]
        if not known_arrays:
            return None
        source = {key: source[key] for key in known_arrays}
    else:
        return None

    accepted: dict[str, list] = {}
    warnings: list[str] = []
    for raw_name, rows in source.items():
        entity = _canonical_filename_entity(str(raw_name))
        if entity is None:
            warnings.append(f"Skipped '{raw_name}': the entity name is not recognized by Elimu Sync.")
            continue
        if entity not in IMPORTABLE_ENTITIES:
            warnings.append(f"Skipped '{raw_name}': school identity, accounts, staff roles and teacher assignments must be linked inside Elimu, not imported as data rows.")
            continue
        if not isinstance(rows, list):
            warnings.append(f"Skipped '{raw_name}': its value must be an array of records.")
            continue
        accepted.setdefault(entity, []).extend(rows)
    return accepted, warnings


def _sanitize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Strip database-local ids, tenant selectors and account/authorization fields."""
    result = dict(record)
    protected = {
        "_id", "school_id", "owner_user_id", "created_by", "updated_by",
        "user_id", "student_user_id", "teacher_user_id", "staff_id",
        "permissions", "access_token", "refresh_token", "password", "password_hash",
        "created_at", "updated_at", "deleted", "deleted_at", "tombstone",
        "source_system", "sync_updated_at",
    }
    compact_protected = {
        "schoolid", "owneruserid", "createdby", "updatedby", "userid",
        "studentuserid", "teacheruserid", "staffid", "accesstoken",
        "refreshtoken", "passwordhash", "createdat", "updatedat",
        "deletedevent", "deletedat", "sourcesystem", "syncupdatedat",
    }
    for key in list(result):
        normalized_key = str(key).casefold()
        compact_key = re.sub(r"[^a-z0-9]", "", normalized_key)
        if (
            normalized_key in protected
            or compact_key in compact_protected
            or normalized_key.endswith(("_password", "_token", "_secret"))
        ):
            result.pop(key, None)
    return result


def _normalize_field_mappings(value: Any) -> dict:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise APIError("Field mappings must be a JSON object.", 422, "invalid_field_mappings")
    # Let the canonical importer/mapper apply and validate the mappings.
    return dict(value)


def _parse_one(data: bytes, filename: str, entity_hint: str | None, field_mappings: Mapping[str, Any], limit: int) -> dict:
    entity = entity_hint
    extension = PurePosixPath(filename).suffix.casefold()
    if extension == ".json":
        document = _json_load(data, filename)
        if isinstance(document, Mapping) and isinstance(document.get("entities"), Mapping):
            raise APIError("This file contains a multi-entity JSON package; upload it directly or inside a ZIP, without selecting one entity.", 422, "nested_migration_bundle")
        detected_entity = _canonical_filename_entity(_text(document.get("entity_type"))) if isinstance(document, Mapping) else None
        # An explicit entity_type in a JSON export is authoritative; the UI
        # selector is only a fallback for raw arrays or CSV/XLSX files.
        entity = detected_entity or entity
    if not entity:
        entity = _canonical_filename_entity(filename)
    if entity and entity not in IMPORTABLE_ENTITIES:
        raise APIError(
            f"'{entity}' is not eligible for data-file import. School, staff, account and teacher-assignment records are managed through Elimu's secure membership workflow.",
            422,
            "protected_import_entity",
        )
    try:
        package = importer.import_package(
            data,
            filename=filename,
            content_type=None,
            entity_type=entity,
            field_mappings=field_mappings,
            limit=max(1, min(int(limit), MAX_IMPORT_ROWS)),
        )
    except APIError:
        raise
    except Exception as exc:
        raise APIError(f"Could not read '{filename}': {exc}", 422, "import_parse_failed") from exc
    resolved = package.get("entity_type") or entity
    if not resolved:
        raise APIError(
            f"Could not determine the data type for '{filename}'. Choose its data type or name it with a recognized entity such as students.csv or classes.xlsx.",
            422,
            "import_entity_required",
        )
    resolved = _canonical_filename_entity(resolved) or resolved
    if resolved not in IMPORTABLE_ENTITIES:
        raise APIError(f"'{resolved}' is not an eligible data import type.", 422, "protected_import_entity")
    return {"entity_type": resolved, "records": package.get("records") or [], "format": package.get("format") or extension.lstrip("."), "metadata": package.get("metadata") or {}, "validation": package.get("validation") or {}}


def _parse_upload(data: bytes, filename: str, content_type: str | None, entity_hint: str | None, field_mappings: Mapping[str, Any]) -> tuple[OrderedDict, list[str], list[str]]:
    if not data:
        raise APIError("The selected import file is empty.", 422, "empty_import_file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise APIError("Import files must be 25 MB or smaller. Split larger exports into smaller ZIP packages.", 413, "import_file_too_large")

    basename = PurePosixPath(filename or "school-export").name or "school-export"
    extension = PurePosixPath(basename).suffix.casefold()
    warnings: list[str] = []
    source_files: list[str] = []
    gathered: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    remaining = MAX_IMPORT_ROWS

    def add_records(entity: str, records: list, source_name: str) -> None:
        nonlocal remaining
        if entity not in IMPORTABLE_ENTITIES:
            warnings.append(f"Skipped {source_name}: '{entity}' is a protected or unsupported entity. Manage school accounts and staff through Elimu instead.")
            return
        if not isinstance(records, list):
            warnings.append(f"Skipped {source_name}: records were not supplied as an array.")
            return
        if len(records) > remaining:
            records = records[:remaining]
            warnings.append(f"The import reached the {MAX_IMPORT_ROWS:,}-record safety limit; additional rows were not staged.")
        normalized_rows: list[dict[str, Any]] = []
        for number, record in enumerate(records, start=1):
            if not isinstance(record, Mapping):
                warnings.append(f"Skipped non-object row {number} in {source_name}.")
                continue
            cleaned = _sanitize_record(record)
            try:
                encoded_size = len(json.dumps(cleaned, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8"))
            except Exception as exc:
                raise APIError(f"A record in {source_name} could not be normalized: {exc}", 422, "invalid_import_record") from exc
            if encoded_size > MAX_RECORD_BYTES:
                raise APIError(f"A record in {source_name} exceeds the safe record size. Remove embedded attachments or very large text fields and retry.", 413, "import_record_too_large")
            normalized_rows.append(cleaned)
        if normalized_rows:
            gathered.setdefault(entity, []).extend(normalized_rows)
            remaining = max(0, remaining - len(normalized_rows))
            source_files.append(source_name)

    def add_bundle_rows(entity: str, rows: list, source_name: str) -> None:
        """Apply the same canonical field mapping used by CSV/XLSX/JSON files."""
        if entity not in IMPORTABLE_ENTITIES:
            add_records(entity, rows, source_name)
            return
        object_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
        if isinstance(rows, list) and len(object_rows) != len(rows):
            warnings.append(f"Skipped {len(rows) - len(object_rows)} non-object rows in {source_name}.")
        if len(object_rows) > remaining:
            warnings.append(f"The import reached the {MAX_IMPORT_ROWS:,}-record safety limit; additional rows were not staged.")
            object_rows = object_rows[:remaining]
        if not object_rows:
            return
        try:
            normalized_rows = importer.normalize_records(
                object_rows,
                entity_type=entity,
                field_mappings=field_mappings,
                limit=len(object_rows),
            )
        except Exception as exc:
            raise APIError(f"Could not normalize records for {entity} in {source_name}: {exc}", 422, "import_normalization_failed") from exc
        add_records(entity, normalized_rows, source_name)

    if extension == ".zip":
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, OSError) as exc:
            raise APIError("The ZIP package could not be opened. Create a standard ZIP archive and try again.", 422, "invalid_import_zip") from exc
        with archive:
            infos = [info for info in archive.infolist() if not info.is_dir() and not PurePosixPath(info.filename).name.startswith(".") and "__MACOSX" not in info.filename.split("/")]
            if len(infos) > MAX_ZIP_FILES:
                raise APIError(f"ZIP packages can contain at most {MAX_ZIP_FILES} files.", 413, "import_zip_file_limit")
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_ZIP_UNPACKED_BYTES:
                raise APIError("The ZIP expands beyond the 80 MB safety limit. Split the export into smaller packages.", 413, "import_zip_too_large")
            compressed_size = max(1, len(data))
            if total_uncompressed / compressed_size > 250:
                raise APIError("The ZIP compression ratio is too high to process safely. Re-export as ordinary CSV/JSON files and retry.", 413, "import_zip_compression_limit")
            for info in infos:
                name = PurePosixPath(info.filename).name
                ext = PurePosixPath(name).suffix.casefold()
                if ext not in {".json", ".csv", ".xlsx"}:
                    warnings.append(f"Skipped {name}: supported formats are JSON, CSV and XLSX.")
                    continue
                raw = archive.read(info)
                if ext == ".json":
                    document = _json_load(raw, name)
                    multi = _migration_entities(document)
                    if multi is not None:
                        entities, bundle_warnings = multi
                        warnings.extend(bundle_warnings)
                        for raw_entity, rows in entities.items():
                            entity = _canonical_filename_entity(raw_entity) or raw_entity
                            add_bundle_rows(entity, rows, name)
                        source_files.append(name)
                        continue
                try:
                    entity_hint = _canonical_filename_entity(name)
                    parsed = _parse_one(raw, name, entity_hint, field_mappings, max(1, remaining))
                    add_records(parsed["entity_type"], parsed["records"], name)
                except APIError as exc:
                    warnings.append(str(exc))
    elif extension in {".json", ".csv", ".xlsx"}:
        if extension == ".json":
            document = _json_load(data, basename)
            multi = _migration_entities(document)
            if multi is not None:
                entities, bundle_warnings = multi
                warnings.extend(bundle_warnings)
                for raw_entity, rows in entities.items():
                    entity = _canonical_filename_entity(raw_entity) or raw_entity
                    add_bundle_rows(entity, rows, basename)
            else:
                parsed = _parse_one(data, basename, _canonical_filename_entity(entity_hint or "") if entity_hint else None, field_mappings, remaining)
                add_records(parsed["entity_type"], parsed["records"], basename)
        else:
            normalized_hint = _canonical_filename_entity(entity_hint or "") if entity_hint else None
            parsed = _parse_one(data, basename, normalized_hint, field_mappings, remaining)
            add_records(parsed["entity_type"], parsed["records"], basename)
    else:
        raise APIError("Choose a ZIP, JSON, CSV or XLSX export file.", 422, "unsupported_import_format")

    if not gathered:
        note = " ".join(warnings[:4])
        raise APIError(
            "No eligible records could be staged. Verify the file format and entity names. " + note,
            422,
            "no_importable_records",
        )

    # Stable order keeps parent entities ahead of common child records.
    ordered: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for entity in ENTITY_ORDER:
        if gathered.get(entity):
            ordered[entity] = gathered[entity]
    for entity, rows in gathered.items():
        if entity not in ordered:
            ordered[entity] = rows
    return ordered, warnings, list(dict.fromkeys(source_files))


def _principal_ready(school_id: str) -> bool:
    member = collection(STAFF_COLLECTION).find_one({
        "school_id": school_id,
        "role": "principal",
        "status": "active",
    })
    if member:
        return True
    current = now_utc()
    for invite in collection(STAFF_INVITATIONS).find({
        "school_id": school_id,
        "role": "principal",
        "status": "invited",
    }).limit(500):
        # A failed delivery is not a real appointment invitation. The owner
        # can use Manage Staff -> Resend email; otherwise an active membership
        # is required before migration begins.
        if (
            invitation_is_usable(invite, current)
            and _text(invite.get("email_status")).lower() == "sent"
        ):
            return True
    return False


def _manifest_view(document: Mapping[str, Any]) -> dict[str, Any]:
    public_keys = (
        "import_id", "filename", "format", "digest", "status", "total_records",
        "total_batches", "completed_batches", "failed_batches", "processed_records",
        "successful_records", "created_records", "updated_records", "conflict_records",
        "error_records", "entities", "source_files", "warnings", "last_error",
        "created_at", "expires_at", "completed_at",
    )
    result = {key: document.get(key) for key in public_keys if key in document}
    result["progress_percent"] = round(100 * int(document.get("completed_batches", 0)) / max(1, int(document.get("total_batches", 0))))
    return result


def _cleanup_expired() -> None:
    now = now_utc()
    expired = list(collection(IMPORTS).find({"expires_at": {"$lt": now}}, {"_id": 1}).limit(50))
    for item in expired:
        import_id = str(item.get("_id", ""))
        collection(IMPORT_BATCHES).delete_many({"import_id": import_id})
        collection(IMPORTS).delete_one({"_id": item["_id"]})


def preview_upload(
    user_id: Any,
    *,
    filename: str,
    data: bytes,
    content_type: str | None = None,
    entity_type: str | None = None,
    field_mappings: Any = None,
) -> dict[str, Any]:
    """Parse, normalize and stage data; this never changes authoritative records."""
    school_id = _authorize_school(user_id)
    if not _text(filename):
        raise APIError("The uploaded file must have a filename.", 422, "import_filename_required")
    mappings = _normalize_field_mappings(field_mappings)
    _cleanup_expired()
    gathered, warnings, source_files = _parse_upload(
        data, filename, content_type, entity_type, mappings
    )

    import_id = secrets.token_urlsafe(18)
    timestamp = now_utc()
    batch_documents: list[dict[str, Any]] = []
    sequence = 0
    entity_summaries = []
    for entity in ENTITY_ORDER:
        rows = gathered.get(entity) or []
        if not rows:
            continue
        field_names = sorted({str(key) for row in rows[:20] for key in row.keys()})[:80]
        entity_summaries.append({"entity_type": entity, "count": len(rows), "fields": field_names})
        current_records: list[dict[str, Any]] = []
        current_bytes = 0
        for record in rows:
            encoded_size = len(json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8"))
            if current_records and (len(current_records) >= MAX_BATCH_RECORDS or current_bytes + encoded_size > MAX_BATCH_BYTES):
                sequence += 1
                batch_documents.append({
                    "import_id": import_id, "school_id": school_id, "entity_type": entity,
                    "sequence": sequence, "status": "pending", "records": current_records,
                    "record_count": len(current_records), "created_at": timestamp, "updated_at": timestamp,
                })
                current_records, current_bytes = [], 0
            current_records.append(record)
            current_bytes += encoded_size
        if current_records:
            sequence += 1
            batch_documents.append({
                "import_id": import_id, "school_id": school_id, "entity_type": entity,
                "sequence": sequence, "status": "pending", "records": current_records,
                "record_count": len(current_records), "created_at": timestamp, "updated_at": timestamp,
            })

    if not batch_documents:
        raise APIError("No records were available to stage for migration.", 422, "empty_import_preview")

    manifest = {
        "_id": import_id,
        "import_id": import_id,
        "school_id": school_id,
        "created_by": str(user_id),
        "filename": PurePosixPath(filename).name[:255],
        "format": PurePosixPath(filename).suffix.lstrip(".").casefold() or "zip",
        "digest": hashlib.sha256(data).hexdigest(),
        "status": "previewed",
        "total_records": sum(len(rows) for rows in gathered.values()),
        "total_batches": len(batch_documents),
        "completed_batches": 0,
        "failed_batches": 0,
        "processed_records": 0,
        "successful_records": 0,
        "created_records": 0,
        "updated_records": 0,
        "conflict_records": 0,
        "error_records": 0,
        "entities": entity_summaries,
        "source_files": source_files,
        "warnings": warnings[:100],
        "field_mappings": mappings,
        "created_at": timestamp,
        "updated_at": timestamp,
        "expires_at": timestamp + IMPORT_TTL,
        "last_error": None,
    }
    try:
        collection(IMPORTS).insert_one(manifest)
        if batch_documents:
            collection(IMPORT_BATCHES).insert_many(batch_documents, ordered=True)
    except Exception as exc:
        collection(IMPORT_BATCHES).delete_many({"import_id": import_id, "school_id": school_id})
        collection(IMPORTS).delete_one({"_id": import_id, "school_id": school_id})
        raise APIError("Could not safely stage this import. No school records were changed. Retry after checking the database connection.", 503, "import_staging_failed") from exc
    return _manifest_view(manifest)


def _get_manifest(school_id: str, import_id: str) -> dict:
    document = collection(IMPORTS).find_one({"_id": import_id, "school_id": school_id})
    if not document:
        raise APIError("Import preview not found for this school. Upload the file again if the preview has expired.", 404, "import_preview_not_found")
    if document.get("expires_at") and document["expires_at"] < now_utc():
        collection(IMPORT_BATCHES).delete_many({"import_id": import_id, "school_id": school_id})
        collection(IMPORTS).delete_one({"_id": import_id, "school_id": school_id})
        raise APIError("This import preview expired. Upload the file again.", 410, "import_preview_expired")
    return document


def start_import(user_id: Any, import_id: str) -> dict[str, Any]:
    school_id = _authorize_school(user_id)
    manifest = _get_manifest(school_id, _text(import_id))
    if manifest.get("status") == "completed":
        return _manifest_view(manifest)
    if not _principal_ready(school_id):
        raise APIError(
            "Before importing legacy records, the School Owner must invite one Principal from Manage Staff. The Principal must already be linked to this school, or the pending invitation must be valid and its email delivery status must be sent. If delivery failed, resend the invitation first.",
            409,
            "principal_required_before_import",
        )
    # Recover a batch whose request was interrupted for long enough to be stale.
    stale_before = now_utc() - timedelta(minutes=15)
    collection(IMPORT_BATCHES).update_many(
        {"import_id": import_id, "school_id": school_id, "status": "processing", "updated_at": {"$lt": stale_before}},
        {"$set": {"status": "pending", "updated_at": now_utc(), "last_error": "Recovered after an interrupted request."}},
    )
    timestamp = now_utc()
    collection(IMPORTS).update_one(
        {"_id": import_id, "school_id": school_id, "status": {"$ne": "completed"}},
        {"$set": {"status": "running", "started_at": manifest.get("started_at") or timestamp, "updated_at": timestamp, "last_error": None}},
    )
    return _manifest_view(_get_manifest(school_id, import_id))


def import_status(user_id: Any, import_id: str) -> dict[str, Any]:
    school_id = _authorize_school(user_id)
    return _manifest_view(_get_manifest(school_id, _text(import_id)))


def _counts(result: Mapping[str, Any], key: str) -> int:
    try:
        return max(0, int(result.get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def process_next_batch(user_id: Any, import_id: str, *, retry_failed: bool = False) -> dict[str, Any]:
    school_id = _authorize_school(user_id)
    manifest = _get_manifest(school_id, _text(import_id))
    if manifest.get("status") == "previewed":
        raise APIError("Start the import after reviewing its preview first.", 409, "import_not_started")
    if manifest.get("status") == "completed":
        return {**_manifest_view(manifest), "complete": True, "needs_retry": False}
    timestamp = now_utc()
    collection(IMPORTS).update_one({"_id": import_id, "school_id": school_id}, {"$set": {"status": "running", "updated_at": timestamp}})

    batch = None
    if retry_failed:
        batch = collection(IMPORT_BATCHES).find_one_and_update(
            {"import_id": import_id, "school_id": school_id, "status": "failed"},
            {"$set": {"status": "processing", "updated_at": timestamp, "last_error": None}, "$inc": {"attempts": 1}},
            sort=[("sequence", 1)], return_document=ReturnDocument.AFTER,
        )
    if batch is None:
        batch = collection(IMPORT_BATCHES).find_one_and_update(
            {"import_id": import_id, "school_id": school_id, "status": "pending"},
            {"$set": {"status": "processing", "updated_at": timestamp, "last_error": None}, "$inc": {"attempts": 1}},
            sort=[("sequence", 1)], return_document=ReturnDocument.AFTER,
        )

    if batch is None:
        pending = collection(IMPORT_BATCHES).count_documents({"import_id": import_id, "school_id": school_id, "status": {"$in": ["pending", "processing"]}})
        failed = collection(IMPORT_BATCHES).count_documents({"import_id": import_id, "school_id": school_id, "status": "failed"})
        status = "paused" if failed else ("completed" if pending == 0 else "running")
        final_updates = {"status": status, "failed_batches": failed, "updated_at": now_utc()}
        if status == "completed":
            final_updates["completed_at"] = now_utc()
        collection(IMPORTS).update_one({"_id": import_id, "school_id": school_id}, {"$set": final_updates})
        latest = _get_manifest(school_id, import_id)
        return {**_manifest_view(latest), "complete": status == "completed", "needs_retry": failed > 0, "message": "Retry failed batches before completing the migration." if failed else None}

    records = batch.get("records") or []
    try:
        # Existing reconciler preserves cloud records, tracks changes, and logs conflicts.
        result = services.ingest(user_id, {
            "entity_type": batch["entity_type"],
            "records": records,
            "source": "legacy_import",
            "trigger": "manual",
            "conflict_strategy": "manual",
            "delete_mode": "ignore",
            "batch_size": min(MAX_BATCH_RECORDS, max(25, len(records))),
        })
        result = result if isinstance(result, Mapping) else {}
        finished = now_utc()
        collection(IMPORT_BATCHES).update_one(
            {"_id": batch["_id"], "import_id": import_id, "school_id": school_id, "status": "processing"},
            {"$set": {"status": "completed", "updated_at": finished, "completed_at": finished, "result": {
                "total": _counts(result, "total"), "created": _counts(result, "created"),
                "updated": _counts(result, "updated") + _counts(result, "merged"),
                "conflicts": _counts(result, "conflicts"), "errors": _counts(result, "errors"),
                "successful": _counts(result, "successful"), "failed": _counts(result, "failed"),
            }}, "$unset": {"last_error": ""}},
        )
        collection(IMPORTS).update_one(
            {"_id": import_id, "school_id": school_id},
            {"$inc": {
                "completed_batches": 1,
                "processed_records": len(records),
                "successful_records": _counts(result, "successful"),
                "created_records": _counts(result, "created"),
                "updated_records": _counts(result, "updated") + _counts(result, "merged"),
                "conflict_records": _counts(result, "conflicts"),
                "error_records": _counts(result, "errors"),
                "failed_batches": -1 if retry_failed and int(manifest.get("failed_batches", 0) or 0) else 0,
            }, "$set": {"updated_at": finished, "last_error": None}},
        )
    except Exception as exc:
        message = _text(getattr(exc, "message", None) or str(exc))[:1200]
        failed_at = now_utc()
        collection(IMPORT_BATCHES).update_one(
            {"_id": batch["_id"], "import_id": import_id, "school_id": school_id},
            {"$set": {"status": "failed", "updated_at": failed_at, "last_error": message}},
        )
        current = _get_manifest(school_id, import_id)
        collection(IMPORTS).update_one(
            {"_id": import_id, "school_id": school_id},
            {"$set": {"status": "paused", "updated_at": failed_at, "last_error": message}, "$inc": {"failed_batches": 1 if not retry_failed else 0}},
        )
        latest = _get_manifest(school_id, import_id)
        return {**_manifest_view(latest), "complete": False, "needs_retry": True, "batch_error": message, "last_batch": {"entity_type": batch.get("entity_type"), "record_count": len(records)}}

    remaining = collection(IMPORT_BATCHES).count_documents({"import_id": import_id, "school_id": school_id, "status": {"$in": ["pending", "processing"]}})
    failed = collection(IMPORT_BATCHES).count_documents({"import_id": import_id, "school_id": school_id, "status": "failed"})
    status = "paused" if failed and remaining == 0 else ("completed" if remaining == 0 else "running")
    final_updates = {"status": status, "failed_batches": failed, "updated_at": now_utc()}
    if status == "completed":
        final_updates["completed_at"] = now_utc()
    collection(IMPORTS).update_one({"_id": import_id, "school_id": school_id}, {"$set": final_updates})
    latest = _get_manifest(school_id, import_id)
    return {
        **_manifest_view(latest),
        "complete": status == "completed",
        "needs_retry": status == "paused",
        "last_batch": {
            "entity_type": batch.get("entity_type"),
            "record_count": len(records),
            "created": _counts(result, "created"),
            "updated": _counts(result, "updated") + _counts(result, "merged"),
            "conflicts": _counts(result, "conflicts"),
            "errors": _counts(result, "errors"),
        },
    }
