# backend/jumuiya/elimu/sync/importer.py

from __future__ import annotations

"""
Elimu synchronization import utilities.

Supported formats
-----------------
- JSON
- CSV
- XLSX

Responsibilities
----------------
- parse external school-system data;
- parse RevelaCode/Elimu export envelopes;
- normalize spreadsheet headers;
- preserve useful scalar types;
- safely decode JSON values embedded in CSV/XLSX;
- validate rows before synchronization;
- provide import previews;
- support school-configurable field mappings;
- keep import transport separate from authoritative persistence.

The importer does NOT write to MongoDB.

Parsed records flow into:

    mapper.py
        ↓
    engine.py
        ↓
    authoritative Elimu collection
"""

import csv
import io
import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional

from .mapper import (
    apply_field_mappings,
    canonical_entity_type,
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
# LIMITS
# =========================================================

MAX_IMPORT_ROWS = 50000
MAX_IMPORT_COLUMNS = 500
MAX_CELL_LENGTH = 100000

DEFAULT_PREVIEW_ROWS = 5
MAX_PREVIEW_ROWS = 50


# =========================================================
# IMPORT SCHEMAS
# =========================================================

JSON_IMPORT_SCHEMA = "elimu-sync-export-v2"


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


def _mapping(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        return {}

    return dict(
        value
    )


def _is_empty(
    value: Any,
) -> bool:
    if value is None:
        return True

    if isinstance(
        value,
        str,
    ):
        return not value.strip()

    return False


def _bounded_rows(
    rows: Iterable[Any],
    *,
    limit: int = MAX_IMPORT_ROWS,
) -> list[Any]:
    maximum = max(
        1,
        min(
            int(limit),
            MAX_IMPORT_ROWS,
        ),
    )

    result: list[Any] = []

    for row in rows:
        if len(result) >= maximum:
            break

        result.append(
            row
        )

    return result


# =========================================================
# HEADER NORMALIZATION
# =========================================================

def normalize_header(
    value: Any,
) -> str:
    """
    Normalize spreadsheet/CSV column names.

    Examples:

        " Student Name " -> "Student Name"
        None             -> ""
    """
    return _text(
        value
    )


def normalize_headers(
    headers: Iterable[Any],
) -> list[str]:
    """
    Normalize and validate headers.

    Blank headers are rejected because silently creating unnamed
    fields makes school imports extremely difficult to diagnose.
    """
    result: list[str] = []
    seen: set[str] = set()

    for index, header in enumerate(
        headers
    ):
        normalized = normalize_header(
            header
        )

        if not normalized:
            raise ValueError(
                f"Import contains a blank column header at position {index + 1}."
            )

        if normalized in seen:
            raise ValueError(
                f"Import contains duplicate column header: '{normalized}'."
            )

        if (
            normalized.startswith("$")
            or "\x00" in normalized
        ):
            raise ValueError(
                f"Invalid import column header: '{normalized}'."
            )

        if len(normalized) > 255:
            raise ValueError(
                f"Import column header is too long: '{normalized}'."
            )

        seen.add(
            normalized
        )

        result.append(
            normalized
        )

    if len(result) > MAX_IMPORT_COLUMNS:
        raise ValueError(
            f"Import contains more than {MAX_IMPORT_COLUMNS} columns."
        )

    return result


# =========================================================
# SCALAR PARSING
# =========================================================

TRUE_VALUES = {
    "true",
    "yes",
    "y",
    "1",
    "on",
}

FALSE_VALUES = {
    "false",
    "no",
    "n",
    "0",
    "off",
}


def _parse_scalar(
    value: Any,
) -> Any:
    """
    Convert common CSV/XLSX string values back into useful Python types.

    Important:
        identifiers with leading zeros are kept as strings.

    Examples:

        "true"        -> True
        "false"       -> False
        "123.50"      -> 123.50
        "2026-10-08"  -> date
        "0712345678"  -> "0712345678"
        ""            -> None
    """
    if value is None:
        return None

    if isinstance(
        value,
        (
            bool,
            int,
            float,
            datetime,
            date,
            Decimal,
        ),
    ):
        # NaN / infinity are not portable synchronization values.
        if isinstance(
            value,
            float,
        ) and not math.isfinite(
            value
        ):
            return None

        return value

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

    text = str(
        value
    ).strip()

    if not text:
        return None

    if len(text) > MAX_CELL_LENGTH:
        raise ValueError(
            "An imported cell exceeds the maximum supported length."
        )

    lowered = text.casefold()

    if lowered in TRUE_VALUES:
        return True

    if lowered in FALSE_VALUES:
        return False

    # JSON object/array embedded in CSV/XLSX.
    if (
        (
            text.startswith("{")
            and text.endswith("}")
        )
        or (
            text.startswith("[")
            and text.endswith("]")
        )
    ):
        try:
            decoded = json.loads(
                text
            )

            if isinstance(
                decoded,
                (dict, list),
            ):
                return normalize(
                    decoded
                )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            pass

    # Keep strings with leading-zero identifiers as text.
    digits_only = text.isdigit()

    if digits_only:
        if len(text) > 1 and text.startswith(
            "0"
        ):
            return text

        try:
            return int(
                text
            )
        except ValueError:
            return text

    # Decimal-looking numbers.
    try:
        if (
            "." in text
            or "e" in lowered
        ):
            number = float(
                text
            )

            if math.isfinite(
                number
            ):
                return number

    except (
        TypeError,
        ValueError,
    ):
        pass

    # ISO date / datetime.
    if "T" in text:
        try:
            return datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError:
            pass

    # Date-only.
    if len(text) == 10:
        try:
            return date.fromisoformat(
                text
            )
        except ValueError:
            pass

    return text


# =========================================================
# RECORD NORMALIZATION
# =========================================================

def normalize_record(
    record: Mapping[str, Any],
    *,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
) -> dict[str, Any]:
    """
    Normalize one imported record and optionally apply a school-specific
    field mapping.
    """
    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            "Each imported record must be an object."
        )

    normalized_source: dict[str, Any] = {}

    for key, value in record.items():
        field = normalize_header(
            key
        )

        if not field:
            continue

        if field.startswith("$"):
            raise ValueError(
                f"Invalid imported field: '{field}'."
            )

        normalized_source[
            field
        ] = _parse_recursive(
            value
        )

    if entity_type:
        canonical = canonical_entity_type(
            entity_type
        )

        normalized_source = apply_field_mappings(
            canonical,
            normalized_source,
            field_mappings,
        )

    return normalize(
        normalized_source
    )


def _parse_recursive(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Mapping,
    ):
        return {
            normalize_header(
                key
            ): _parse_recursive(
                item
            )
            for key, item in value.items()
            if normalize_header(
                key
            )
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _parse_recursive(
                item
            )
            for item in value
        ]

    return _parse_scalar(
        value
    )


def normalize_records(
    records: Iterable[
        Mapping[str, Any]
    ],
    *,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    limit: int = MAX_IMPORT_ROWS,
) -> list[dict[str, Any]]:
    """
    Normalize a bounded collection of imported records.
    """
    bounded = _bounded_rows(
        records,
        limit=limit,
    )

    result: list[
        dict[str, Any]
    ] = []

    for index, record in enumerate(
        bounded
    ):
        try:
            result.append(
                normalize_record(
                    record,
                    entity_type=entity_type,
                    field_mappings=field_mappings,
                )
            )
        except ValueError as exc:
            raise ValueError(
                f"Invalid imported record at row {index + 1}: {exc}"
            ) from exc

    return result


# =========================================================
# CSV PARSING
# =========================================================

def _csv_dialect(
    delimiter: str = ",",
) -> csv.Dialect:
    """
    Build a strict CSV dialect.
    """
    if (
        not isinstance(
            delimiter,
            str,
        )
        or len(delimiter) != 1
    ):
        raise ValueError(
            "CSV delimiter must be one character."
        )

    class ElimuDialect(csv.excel):
        pass

    ElimuDialect.delimiter = delimiter

    return ElimuDialect()


def parse_csv(
    text: str,
    *,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    delimiter: str = ",",
    limit: int = MAX_IMPORT_ROWS,
) -> list[dict[str, Any]]:
    """
    Parse CSV text into canonical-ready records.

    UTF-8 BOM is supported.
    """
    if not isinstance(
        text,
        str,
    ):
        raise ValueError(
            "CSV input must be text."
        )

    # Remove UTF-8 BOM if present.
    text = text.lstrip(
        "\ufeff"
    )

    if not text.strip():
        return []

    reader = csv.reader(
        io.StringIO(
            text,
            newline="",
        ),
        dialect=_csv_dialect(
            delimiter
        ),
    )

    try:
        rows = list(
            reader
        )
    except csv.Error as exc:
        raise ValueError(
            f"Invalid CSV input: {exc}"
        ) from exc

    if not rows:
        return []

    headers = normalize_headers(
        rows[0]
    )

    result: list[
        dict[str, Any]
    ] = []

    for row_number, row in enumerate(
        rows[1:],
        start=2,
    ):
        # Completely blank rows are ignored.
        if not any(
            not _is_empty(
                value
            )
            for value in row
        ):
            continue

        if len(row) > len(
            headers
        ):
            raise ValueError(
                f"CSV row {row_number} has more values than the header."
            )

        padded = list(
            row
        )

        while len(
            padded
        ) < len(headers):
            padded.append(
                None
            )

        record = {
            headers[index]: padded[index]
            for index in range(
                len(headers)
            )
        }

        result.append(
            normalize_record(
                record,
                entity_type=entity_type,
                field_mappings=field_mappings,
            )
        )

        if len(
            result
        ) >= min(
            int(limit),
            MAX_IMPORT_ROWS,
        ):
            break

    return result


# =========================================================
# JSON PARSING
# =========================================================

def _extract_json_records(
    data: Any,
) -> tuple[
    list[Any],
    dict[str, Any],
]:
    """
    Accept:

        [record, record]

    and the Elimu export envelope:

        {
            "schema": "elimu-sync-export-v2",
            "entity_type": "students",
            "school_id": "...",
            "count": 123,
            "records": [...]
        }
    """
    if isinstance(
        data,
        list,
    ):
        return (
            data,
            {},
        )

    if isinstance(
        data,
        Mapping,
    ):
        records = data.get(
            "records"
        )

        if not isinstance(
            records,
            list,
        ):
            raise ValueError(
                "JSON import object must contain a records array."
            )

        metadata = {
            str(key): value
            for key, value in data.items()
            if key != "records"
        }

        schema = metadata.get(
            "schema"
        )

        if schema not in {
            None,
            JSON_IMPORT_SCHEMA,
        }:
            raise ValueError(
                f"Unsupported Elimu JSON import schema: {schema}"
            )

        return (
            records,
            metadata,
        )

    raise ValueError(
        "JSON import must contain an array of records or an Elimu export envelope."
    )


def parse_json(
    text: str,
    *,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    limit: int = MAX_IMPORT_ROWS,
    return_metadata: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Parse JSON records or an Elimu Sync JSON export envelope.

    Backward-compatible use:

        parse_json(text)
    """
    if not isinstance(
        text,
        str,
    ):
        raise ValueError(
            "JSON input must be text."
        )

    text = text.lstrip(
        "\ufeff"
    ).strip()

    if not text:
        return [] if not return_metadata else {
            "records": [],
            "metadata": {},
        }

    try:
        data = json.loads(
            text
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON input: {exc.msg} "
            f"at line {exc.lineno}, column {exc.colno}."
        ) from exc

    raw_records, metadata = (
        _extract_json_records(
            data
        )
    )

    envelope_entity = _text(
        metadata.get(
            "entity_type"
        )
    )

    effective_entity_type = (
        entity_type
        or envelope_entity
        or None
    )

    normalized = normalize_records(
        [
            item
            for item in raw_records
            if isinstance(
                item,
                Mapping,
            )
        ],
        entity_type=effective_entity_type,
        field_mappings=field_mappings,
        limit=limit,
    )

    # Reject the count mismatch in an envelope rather than silently
    # pretending the export was complete.
    declared_count = metadata.get(
        "count"
    )

    if declared_count is not None:
        try:
            declared_count = int(
                declared_count
            )
        except (
            TypeError,
            ValueError,
        ):
            declared_count = None

        if (
            declared_count is not None
            and declared_count
            != len(
                raw_records
            )
        ):
            raise ValueError(
                "JSON export count does not match the number of records."
            )

    if return_metadata:
        return {
            "records": normalized,
            "metadata": metadata,
        }

    return normalized


# =========================================================
# XLSX PARSING
# =========================================================

def parse_xlsx(
    data: bytes,
    *,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    sheet_name: Optional[str] = None,
    limit: int = MAX_IMPORT_ROWS,
) -> list[dict[str, Any]]:
    """
    Parse an XLSX workbook.

    The first row is treated as the header row unless an explicitly
    named worksheet is supplied.
    """
    if not isinstance(
        data,
        (
            bytes,
            bytearray,
            memoryview,
        ),
    ):
        raise ValueError(
            "XLSX input must be bytes."
        )

    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required for XLSX imports."
        ) from exc

    try:
        workbook = load_workbook(
            io.BytesIO(
                bytes(
                    data
                )
            ),
            read_only=True,
            data_only=True,
        )
    except Exception as exc:
        raise ValueError(
            f"Unable to read XLSX workbook: {exc}"
        ) from exc

    try:
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                raise ValueError(
                    f"Worksheet '{sheet_name}' was not found."
                )

            worksheet = workbook[
                sheet_name
            ]

        else:
            if not workbook.sheetnames:
                return []

            worksheet = workbook.active

        rows = worksheet.iter_rows(
            values_only=True
        )

        try:
            raw_headers = next(
                rows
            )
        except StopIteration:
            return []

        headers = normalize_headers(
            raw_headers
        )

        result: list[
            dict[str, Any]
        ] = []

        for row_number, row in enumerate(
            rows,
            start=2,
        ):
            values = list(
                row
            )

            if not any(
                not _is_empty(
                    value
                )
                for value in values
            ):
                continue

            if len(values) > len(
                headers
            ):
                raise ValueError(
                    f"Worksheet row {row_number} has more values than the header."
                )

            while len(values) < len(
                headers
            ):
                values.append(
                    None
                )

            record = {
                headers[index]: values[index]
                for index in range(
                    len(headers)
                )
            }

            result.append(
                normalize_record(
                    record,
                    entity_type=entity_type,
                    field_mappings=field_mappings,
                )
            )

            if len(
                result
            ) >= min(
                int(limit),
                MAX_IMPORT_ROWS,
            ):
                break

        return result

    finally:
        workbook.close()


# =========================================================
# FORMAT AUTO-DETECTION
# =========================================================

def detect_format(
    value: Any,
    *,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> str:
    """
    Detect import format from filename/content type/content.

    Returns:

        json
        csv
        xlsx
    """
    name = _text(
        filename
    ).lower()

    mime = _text(
        content_type
    ).lower()

    if name.endswith(
        ".json"
    ) or "application/json" in mime:
        return "json"

    if name.endswith(
        ".csv"
    ) or "text/csv" in mime:
        return "csv"

    if name.endswith(
        ".xlsx"
    ) or (
        "spreadsheetml"
        in mime
    ):
        return "xlsx"

    if isinstance(
        value,
        (
            bytes,
            bytearray,
        ),
    ):
        leading = bytes(
            value
        ).lstrip()

        if leading.startswith(
            b"{"
        ) or leading.startswith(
            b"["
        ):
            return "json"

        if leading.startswith(
            b"PK"
        ):
            return "xlsx"

        try:
            value = bytes(
                value
            ).decode(
                "utf-8-sig"
            )
        except UnicodeDecodeError:
            pass

    if isinstance(
        value,
        str,
    ):
        stripped = value.lstrip()

        if stripped.startswith(
            "{"
        ) or stripped.startswith(
            "["
        ):
            return "json"

        if "\n" in value or "," in value:
            return "csv"

    raise ValueError(
        "Unable to detect import format. Specify json, csv or xlsx explicitly."
    )


# =========================================================
# GENERIC IMPORT
# =========================================================

def parse(
    data: Any,
    format_name: Optional[str] = None,
    *,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    delimiter: str = ",",
    sheet_name: Optional[str] = None,
    limit: int = MAX_IMPORT_ROWS,
) -> list[dict[str, Any]]:
    """
    Generic parser for JSON/CSV/XLSX.
    """
    normalized_format = (
        _text(
            format_name
        ).lower()
        if format_name
        else detect_format(
            data,
            filename=filename,
            content_type=content_type,
        )
    )

    if normalized_format == "json":
        if isinstance(
            data,
            (
                bytes,
                bytearray,
            ),
        ):
            data = bytes(
                data
            ).decode(
                "utf-8-sig"
            )

        return parse_json(
            str(
                data
            ),
            entity_type=entity_type,
            field_mappings=field_mappings,
            limit=limit,
        )

    if normalized_format == "csv":
        if isinstance(
            data,
            (
                bytes,
                bytearray,
            ),
        ):
            data = bytes(
                data
            ).decode(
                "utf-8-sig"
            )

        return parse_csv(
            str(
                data
            ),
            entity_type=entity_type,
            field_mappings=field_mappings,
            delimiter=delimiter,
            limit=limit,
        )

    if normalized_format in {
        "xlsx",
        "excel",
        "excel_xlsx",
    }:
        if isinstance(
            data,
            str,
        ):
            raise ValueError(
                "XLSX input must be binary data."
            )

        return parse_xlsx(
            bytes(
                data
            ),
            entity_type=entity_type,
            field_mappings=field_mappings,
            sheet_name=sheet_name,
            limit=limit,
        )

    raise ValueError(
        "Unsupported import format. "
        "Use json, csv or xlsx."
    )


# =========================================================
# VALIDATE IMPORTED RECORDS
# =========================================================

def validate_records(
    records: Iterable[
        Mapping[str, Any]
    ],
    *,
    entity_type: Optional[str] = None,
    required_fields: Optional[
        Iterable[str]
    ] = None,
) -> dict[str, Any]:
    """
    Perform transport-level validation before passing records to
    the synchronization engine.

    This does not replace Elimu domain validation in engine/services.
    """
    if entity_type:
        canonical_entity_type(
            entity_type
        )

    required = [
        _text(
            field
        )
        for field in (
            required_fields or []
        )
        if _text(
            field
        )
    ]

    checked = 0
    valid = 0
    errors: list[
        dict[str, Any]
    ] = []

    for index, record in enumerate(
        records
    ):
        checked += 1

        if not isinstance(
            record,
            Mapping,
        ):
            errors.append(
                {
                    "row": index + 1,
                    "error": "Record must be an object.",
                }
            )
            continue

        missing = [
            field
            for field in required
            if (
                field not in record
                or _is_empty(
                    record.get(
                        field
                    )
                )
            )
        ]

        if missing:
            errors.append(
                {
                    "row": index + 1,
                    "error": "Required fields are missing.",
                    "fields": missing,
                }
            )
            continue

        valid += 1

    return {
        "rows": checked,
        "valid": valid,
        "invalid": len(
            errors
        ),
        "valid_all": not errors,
        "errors": errors,
    }


# =========================================================
# PREVIEW
# =========================================================

def preview(
    records: Iterable[
        Mapping[str, Any]
    ],
    *,
    sample_size: int = DEFAULT_PREVIEW_ROWS,
    entity_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a safe import preview.

    No database writes occur here.
    """
    rows = [
        dict(
            record
        )
        for record in records
        if isinstance(
            record,
            Mapping,
        )
    ]

    size = max(
        1,
        min(
            int(
                sample_size
            ),
            MAX_PREVIEW_ROWS,
        ),
    )

    columns = sorted(
        {
            str(
                key
            )
            for record in rows
            for key in record.keys()
        },
        key=lambda value: (
            value.casefold(),
            value,
        ),
    )

    sample = rows[
        :size
    ]

    validation = validate_records(
        rows,
        entity_type=entity_type,
    )

    return {
        "rows": len(
            rows
        ),
        "columns": columns,
        "column_count": len(
            columns
        ),
        "sample": sample,
        "sample_count": len(
            sample
        ),
        "validation": validation,
    }


# =========================================================
# IMPORT PREVIEW FROM RAW DATA
# =========================================================

def preview_import(
    data: Any,
    *,
    format_name: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    delimiter: str = ",",
    sheet_name: Optional[str] = None,
    sample_size: int = DEFAULT_PREVIEW_ROWS,
    limit: int = MAX_IMPORT_ROWS,
) -> dict[str, Any]:
    """
    Parse + preview an import without persisting anything.
    """
    metadata: dict[str, Any] = {}

    if (
        format_name
        and _text(
            format_name
        ).lower()
        == "json"
    ):
        parsed = parse_json(
            data.decode(
                "utf-8-sig"
            )
            if isinstance(
                data,
                (
                    bytes,
                    bytearray,
                ),
            )
            else data,
            entity_type=entity_type,
            field_mappings=field_mappings,
            limit=limit,
            return_metadata=True,
        )

        records = parsed[
            "records"
        ]

        metadata = parsed[
            "metadata"
        ]

    else:
        records = parse(
            data,
            format_name,
            filename=filename,
            content_type=content_type,
            entity_type=entity_type,
            field_mappings=field_mappings,
            delimiter=delimiter,
            sheet_name=sheet_name,
            limit=limit,
        )

    result = preview(
        records,
        sample_size=sample_size,
        entity_type=entity_type,
    )

    result[
        "format"
    ] = (
        _text(
            format_name
        ).lower()
        if format_name
        else detect_format(
            data,
            filename=filename,
            content_type=content_type,
        )
    )

    if metadata:
        result[
            "metadata"
        ] = normalize(
            metadata
        )

    return result


# =========================================================
# IMPORT PACKAGE
# =========================================================

def import_package(
    data: Any,
    *,
    format_name: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    delimiter: str = ",",
    sheet_name: Optional[str] = None,
    limit: int = MAX_IMPORT_ROWS,
) -> dict[str, Any]:
    """
    Full transport import package.

    Returns parsed records plus metadata and validation state.

    No MongoDB writes occur.
    """
    metadata: dict[str, Any] = {}

    detected_format = (
        _text(
            format_name
        ).lower()
        if format_name
        else detect_format(
            data,
            filename=filename,
            content_type=content_type,
        )
    )

    if detected_format == "json":
        raw_json = (
            bytes(
                data
            ).decode(
                "utf-8-sig"
            )
            if isinstance(
                data,
                (
                    bytes,
                    bytearray,
                ),
            )
            else data
        )

        parsed = parse_json(
            raw_json,
            entity_type=entity_type,
            field_mappings=field_mappings,
            limit=limit,
            return_metadata=True,
        )

        records = parsed[
            "records"
        ]

        metadata = parsed[
            "metadata"
        ]

    else:
        records = parse(
            data,
            detected_format,
            filename=filename,
            content_type=content_type,
            entity_type=entity_type,
            field_mappings=field_mappings,
            delimiter=delimiter,
            sheet_name=sheet_name,
            limit=limit,
        )

    validation = validate_records(
        records,
        entity_type=entity_type,
    )

    return {
        "format": detected_format,
        "entity_type": (
            canonical_entity_type(
                entity_type
            )
            if entity_type
            else (
                _text(
                    metadata.get(
                        "entity_type"
                    )
                )
                or None
            )
        ),
        "school_id": (
            _text(
                metadata.get(
                    "school_id"
                )
            )
            or None
        ),
        "count": len(
            records
        ),
        "records": records,
        "metadata": normalize(
            metadata
        ),
        "validation": validation,
        "ready_for_sync": validation[
            "valid_all"
        ],
    }