# backend/jumuiya/elimu/sync/exporter.py

from __future__ import annotations

"""
Elimu synchronization export utilities.

Supported formats
-----------------
- JSON
- CSV
- XLSX

Design goals
------------
- deterministic output;
- safe recursive serialization;
- Mongo ObjectId compatibility;
- datetime/date compatibility;
- nested-record support for CSV/XLSX;
- stable field ordering;
- sync metadata exclusion;
- optional Mongo `_id` inclusion;
- optional envelope metadata.

This module is format/transport focused.

Authoritative record selection belongs to services.py.
"""

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional

from .mapper import (
    canonical_entity_type,
    comparable_record,
    normalize,
)


# =========================================================
# OPTIONAL BSON
# =========================================================

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None  # type: ignore


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_ENCODING = "utf-8"

DEFAULT_CSV_DELIMITER = ","

MAX_EXPORT_ROWS = 10000

# Fields that are synchronization metadata rather than business data.
SYNC_METADATA_FIELDS = {
    "source_system",
    "sync_updated_at",
}

# Mongo's local database identity should normally not leave the system.
MONGO_LOCAL_FIELDS = {
    "_id",
}


# =========================================================
# BASIC HELPERS
# =========================================================

def _text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def _as_record(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            "Every exported record must be an object."
        )

    return dict(
        value
    )


# =========================================================
# PORTABLE SERIALIZATION
# =========================================================

def serialize_value(
    value: Any,
) -> Any:
    """
    Convert Mongo/Python values into portable JSON/CSV/XLSX values.
    """
    if value is None:
        return None

    if (
        ObjectId is not None
        and isinstance(
            value,
            ObjectId,
        )
    ):
        return str(
            value
        )

    if isinstance(
        value,
        datetime,
    ):
        current = value

        if current.tzinfo is None:
            current = current.replace(
                tzinfo=__import__(
                    "datetime"
                ).timezone.utc
            )
        else:
            current = current.astimezone(
                __import__(
                    "datetime"
                ).timezone.utc
            )

        return current.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return format(
            value,
            "f",
        )

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): serialize_value(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            serialize_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        set,
    ):
        return [
            serialize_value(
                item
            )
            for item in sorted(
                value,
                key=lambda item: repr(item),
            )
        ]

    if isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    return str(
        value
    )


# =========================================================
# RECORD PREPARATION
# =========================================================

def prepare_record(
    record: Mapping[str, Any],
    *,
    include_mongo_id: bool = False,
    include_sync_metadata: bool = False,
) -> dict[str, Any]:
    """
    Prepare one record for external export.

    Mongo `_id` is excluded by default.

    Volatile synchronization metadata is excluded by default.
    """
    source = _as_record(
        record
    )

    result: dict[str, Any] = {}

    for key, value in source.items():
        key_text = str(
            key
        )

        if (
            not include_mongo_id
            and key_text in MONGO_LOCAL_FIELDS
        ):
            continue

        if (
            not include_sync_metadata
            and key_text in SYNC_METADATA_FIELDS
        ):
            continue

        result[
            key_text
        ] = serialize_value(
            value
        )

    return result


def prepare_records(
    records: Iterable[Any],
    *,
    include_mongo_id: bool = False,
    include_sync_metadata: bool = False,
    limit: int = MAX_EXPORT_ROWS,
) -> list[dict[str, Any]]:
    """
    Prepare a bounded list of exportable records.
    """
    result: list[
        dict[str, Any]
    ] = []

    maximum = max(
        1,
        min(
            int(
                limit
            ),
            MAX_EXPORT_ROWS,
        ),
    )

    for record in records:
        if len(
            result
        ) >= maximum:
            break

        result.append(
            prepare_record(
                _as_record(
                    record
                ),
                include_mongo_id=include_mongo_id,
                include_sync_metadata=include_sync_metadata,
            )
        )

    return result


# =========================================================
# NESTED FIELD FLATTENING
# =========================================================

def _flatten_value(
    value: Any,
    prefix: str = "",
) -> dict[str, Any]:
    """
    Flatten nested structures into CSV/XLSX-friendly columns.

    Example:

        {
            "guardian": {
                "name": "John",
                "phone": "0712..."
            }
        }

    becomes:

        guardian.name
        guardian.phone
    """
    result: dict[str, Any] = {}

    if isinstance(
        value,
        Mapping,
    ):
        if not value:
            if prefix:
                result[
                    prefix
                ] = ""

            return result

        for key in sorted(
            value.keys(),
            key=lambda item: str(item),
        ):
            key_text = str(
                key
            )

            path = (
                f"{prefix}.{key_text}"
                if prefix
                else key_text
            )

            result.update(
                _flatten_value(
                    value[key],
                    path,
                )
            )

        return result

    if isinstance(
        value,
        (list, tuple),
    ):
        if not value:
            if prefix:
                result[
                    prefix
                ] = ""

            return result

        # Lists are represented as JSON strings in flat exports rather
        # than creating unstable columns based on array length.
        result[
            prefix
        ] = json.dumps(
            serialize_value(
                value
            ),
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

        return result

    if isinstance(
        value,
        set,
    ):
        result[
            prefix
        ] = json.dumps(
            serialize_value(
                value
            ),
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

        return result

    if prefix:
        result[
            prefix
        ] = serialize_value(
            value
        )

    return result


def flatten_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    return _flatten_value(
        prepare_record(
            record,
            include_mongo_id=False,
            include_sync_metadata=False,
        )
    )


def flatten_records(
    records: Iterable[
        Mapping[str, Any]
    ],
) -> list[
    dict[str, Any]
]:
    return [
        flatten_record(
            record
        )
        for record in records
    ]


# =========================================================
# FIELD ORDERING
# =========================================================

def field_names(
    rows: Iterable[
        Mapping[str, Any]
    ],
) -> list[str]:
    """
    Produce deterministic column order.

    Identity/ownership fields appear first, followed by the rest
    alphabetically.
    """
    fields: set[str] = set()

    for row in rows:
        fields.update(
            str(key)
            for key in row.keys()
        )

    priority = {
        "school_id": 0,
        "staff_id": 1,
        "user_id": 2,
        "teacher_user_id": 3,
        "student_id": 4,
        "admission_number": 5,
        "class_id": 6,
        "subject": 7,
        "date": 8,
        "updated_at": 9,
        "created_at": 10,
    }

    return sorted(
        fields,
        key=lambda field: (
            priority.get(
                field,
                1000,
            ),
            field.casefold(),
            field,
        ),
    )


# =========================================================
# JSON EXPORT
# =========================================================

def json_export(
    records: Iterable[Any],
    *,
    entity_type: Optional[str] = None,
    school_id: Any = None,
    include_mongo_id: bool = False,
    include_sync_metadata: bool = False,
    envelope: bool = False,
    indent: int = 2,
) -> str:
    """
    Export records as deterministic UTF-8 JSON.

    Backward-compatible use:

        json_export(records)
    """
    prepared = prepare_records(
        records,
        include_mongo_id=include_mongo_id,
        include_sync_metadata=include_sync_metadata,
    )

    if envelope:
        canonical_entity = (
            canonical_entity_type(
                entity_type
            )
            if entity_type
            else None
        )

        payload = {
            "schema": "elimu-sync-export-v2",
            "entity_type": canonical_entity,
            "school_id": (
                _text(
                    school_id
                )
                or None
            ),
            "count": len(
                prepared
            ),
            "records": prepared,
        }

    else:
        payload = prepared

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=indent,
        default=str,
        sort_keys=True,
    )


# =========================================================
# CSV EXPORT
# =========================================================

def csv_export(
    records: Iterable[Any],
    *,
    delimiter: str = DEFAULT_CSV_DELIMITER,
    include_header: bool = True,
    include_mongo_id: bool = False,
    include_sync_metadata: bool = False,
    encoding: str = DEFAULT_ENCODING,
) -> str:
    """
    Export records as flat CSV.

    Nested dictionaries become dotted columns.

    Lists are serialized as JSON strings so importing the CSV does not
    lose their structure.
    """
    prepared = prepare_records(
        records,
        include_mongo_id=include_mongo_id,
        include_sync_metadata=include_sync_metadata,
    )

    rows = flatten_records(
        prepared
    )

    fields = field_names(
        rows
    )

    output = io.StringIO(
        newline=""
    )

    if not fields:
        return ""

    writer = csv.DictWriter(
        output,
        fieldnames=fields,
        delimiter=delimiter,
        extrasaction="ignore",
        lineterminator="\n",
    )

    if include_header:
        writer.writeheader()

    for row in rows:
        writer.writerow(
            {
                field: row.get(
                    field,
                    "",
                )
                for field in fields
            }
        )

    return output.getvalue()


# =========================================================
# XLSX EXPORT
# =========================================================

def xlsx_export(
    records: Iterable[Any],
    *,
    sheet_name: str = "Elimu Sync",
    include_mongo_id: bool = False,
    include_sync_metadata: bool = False,
) -> bytes:
    """
    Export records as an XLSX workbook.

    Requires openpyxl, which is already used by Elimu's importer.
    """
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required for XLSX export."
        ) from exc

    prepared = prepare_records(
        records,
        include_mongo_id=include_mongo_id,
        include_sync_metadata=include_sync_metadata,
    )

    rows = flatten_records(
        prepared
    )

    fields = field_names(
        rows
    )

    workbook = Workbook()

    worksheet = workbook.active

    worksheet.title = (
        _text(
            sheet_name
        )
        or "Elimu Sync"
    )[:31]

    if fields:
        worksheet.append(
            fields
        )

        for row in rows:
            worksheet.append(
                [
                    row.get(
                        field,
                        "",
                    )
                    for field in fields
                ]
            )

    # Freeze header row.
    if fields:
        worksheet.freeze_panes = "A2"

        # Basic readable widths, bounded to avoid huge columns.
        for column_cells in worksheet.columns:
            values = [
                str(
                    cell.value
                )
                for cell in column_cells
                if cell.value is not None
            ]

            width = min(
                max(
                    len(value)
                    for value in values
                )
                + 2
                if values
                else 10,
                60,
            )

            column_letter = (
                column_cells[0]
                .column_letter
            )

            worksheet.column_dimensions[
                column_letter
            ].width = width

    buffer = io.BytesIO()

    workbook.save(
        buffer
    )

    return buffer.getvalue()


# =========================================================
# GENERIC EXPORT
# =========================================================

def export_records(
    records: Iterable[Any],
    format_name: str = "json",
    **kwargs: Any,
) -> str | bytes:
    """
    Dispatch export based on format.

    Supported:

        json
        csv
        xlsx
        excel
    """
    normalized = (
        _text(
            format_name,
            "json",
        )
        .lower()
    )

    if normalized == "json":
        return json_export(
            records,
            **kwargs,
        )

    if normalized == "csv":
        return csv_export(
            records,
            **kwargs,
        )

    if normalized in {
        "xlsx",
        "excel",
        "excel_xlsx",
    }:
        return xlsx_export(
            records,
            **kwargs,
        )

    raise ValueError(
        "Unsupported export format. "
        "Use json, csv or xlsx."
    )


# =========================================================
# EXPORT MANIFEST
# =========================================================

def export_manifest(
    entity_type: str,
    records: Iterable[
        Mapping[str, Any]
    ],
    *,
    school_id: Any = None,
    source: str = "elimu",
    format_name: str = "json",
) -> dict[str, Any]:
    """
    Generate metadata describing an export package.
    """
    canonical = canonical_entity_type(
        entity_type
    )

    prepared = prepare_records(
        records
    )

    return {
        "schema": "elimu-sync-export-v2",
        "entity_type": canonical,
        "school_id": (
            _text(
                school_id
            )
            or None
        ),
        "source": (
            _text(
                source
            )
            or "elimu"
        ),
        "format": (
            _text(
                format_name
            )
            .lower()
            or "json"
        ),
        "count": len(
            prepared
        ),
        "generated_at": datetime.now(
            __import__(
                "datetime"
            ).timezone.utc
        ).isoformat(),
        "fields": field_names(
            flatten_records(
                prepared
            )
        ),
    }