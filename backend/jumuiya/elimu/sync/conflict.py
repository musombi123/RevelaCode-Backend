# backend/jumuiya/elimu/sync/conflict.py

from __future__ import annotations

"""
Conflict detection and resolution for Elimu synchronization.

Responsibilities
----------------
- deterministic record comparison;
- revision-aware conflict detection;
- nested field-level change detection;
- tombstone/delete conflict handling;
- three-way merge using a common base;
- safe local/cloud resolution;
- support for configured Sync strategies.

The conflict module does NOT write to MongoDB.
Persistence belongs to services/engine.
"""

from copy import deepcopy
from datetime import date, datetime
from typing import Any, Mapping, Optional

from .mapper import (
    canonical_entity_type,
    comparable_record,
    is_deleted_record,
    normalize,
    record_revision,
    record_updated_at,
)


# =========================================================
# SENTINEL
# =========================================================

_MISSING = object()


# =========================================================
# BASIC HELPERS
# =========================================================

def _as_mapping(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        return {}

    return dict(value)


def _same(
    left: Any,
    right: Any,
) -> bool:
    """
    Deterministic equality after Sync normalization.
    """
    return normalize(left) == normalize(right)


# =========================================================
# REVISION / TIMESTAMP ORDERING
# =========================================================

def _timestamp_value(
    value: Any,
) -> Optional[float]:
    """
    Convert supported timestamps into UTC epoch seconds.

    Returns None when a value cannot safely be interpreted.
    """
    if value is None:
        return None

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

        return current.timestamp()

    if isinstance(
        value,
        date,
    ):
        return datetime(
            value.year,
            value.month,
            value.day,
        ).timestamp()

    if isinstance(
        value,
        (int, float),
    ) and not isinstance(
        value,
        bool,
    ):
        return float(value)

    if isinstance(
        value,
        str,
    ):
        text = value.strip()

        if not text:
            return None

        # ISO-8601 support.
        try:
            parsed = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=__import__(
                        "datetime"
                    ).timezone.utc
                )
            else:
                parsed = parsed.astimezone(
                    __import__(
                        "datetime"
                    ).timezone.utc
                )

            return parsed.timestamp()

        except ValueError:
            pass

        # Numeric string fallback.
        try:
            return float(text)

        except ValueError:
            return None

    return None


def _revision(
    record: Mapping[str, Any],
) -> Optional[int]:
    return record_revision(
        record
    )


def _timestamp(
    record: Mapping[str, Any],
) -> Optional[float]:
    return _timestamp_value(
        record_updated_at(
            record
        )
    )


def _stamp(
    record: Mapping[str, Any],
) -> tuple[int, int, float]:
    """
    Build a sortable version stamp.

    Priority:
        1. explicit revision/version;
        2. updated timestamp;
        3. zero fallback.

    The tuple structure prevents accidental comparison of a datetime
    with an integer or string.
    """
    revision = _revision(
        record
    )

    timestamp = _timestamp(
        record
    )

    return (
        1 if revision is not None else 0,
        revision if revision is not None else -1,
        timestamp if timestamp is not None else 0.0,
    )


def compare_stamps(
    local: Mapping[str, Any],
    cloud: Mapping[str, Any],
) -> int:
    """
    Return:

        1   local newer
        0   identical/equal stamp
        -1  cloud newer
    """
    local_stamp = _stamp(
        local
    )

    cloud_stamp = _stamp(
        cloud
    )

    if local_stamp > cloud_stamp:
        return 1

    if local_stamp < cloud_stamp:
        return -1

    return 0


# =========================================================
# NESTED FIELD WALKING
# =========================================================

def _walk(
    value: Any,
    prefix: str = "",
) -> dict[str, Any]:
    """
    Flatten nested mappings/lists into deterministic paths.

    Examples:

        profile.phone
        profile.address.county
        subjects[0]
        subjects[1]
    """
    result: dict[str, Any] = {}

    if isinstance(
        value,
        Mapping,
    ):
        if not value:
            if prefix:
                result[prefix] = {}

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
                _walk(
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
                result[prefix] = []

            return result

        for index, item in enumerate(
            value
        ):
            path = (
                f"{prefix}[{index}]"
                if prefix
                else f"[{index}]"
            )

            result.update(
                _walk(
                    item,
                    path,
                )
            )

        return result

    if prefix:
        result[prefix] = normalize(
            value
        )

    return result


def changed_fields(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> set[str]:
    """
    Return field paths whose values changed.

    Comparison ignores synchronization-only metadata and Mongo's
    database-local `_id`.
    """
    left = comparable_record(
        before or {}
    )

    right = comparable_record(
        after or {}
    )

    left_flat = _walk(
        left
    )

    right_flat = _walk(
        right
    )

    fields = (
        set(left_flat)
        | set(right_flat)
    )

    changed: set[str] = set()

    for field in fields:
        left_value = left_flat.get(
            field,
            _MISSING,
        )
        right_value = right_flat.get(
            field,
            _MISSING,
        )

        if left_value is _MISSING:
            changed.add(field)
            continue

        if right_value is _MISSING:
            changed.add(field)
            continue

        if not _same(
            left_value,
            right_value,
        ):
            changed.add(field)

    return changed


# =========================================================
# FIELD VALUE LOOKUP
# =========================================================

def _get_path(
    document: Mapping[str, Any],
    path: str,
) -> Any:
    """
    Read a flattened path generated by _walk().

    Supports dotted mappings. Array indexes are handled conservatively.
    """
    if not path:
        return _MISSING

    current: Any = document

    parts = path.split(".")

    for part in parts:
        # Array index support.
        if "[" in part:
            head = part.split(
                "[",
                1,
            )[0]

            if head:
                if not isinstance(
                    current,
                    Mapping,
                ):
                    return _MISSING

                current = current.get(
                    head,
                    _MISSING,
                )

                if current is _MISSING:
                    return _MISSING

            remainder = part[
                len(head):
            ]

            while remainder:
                if not remainder.startswith(
                    "["
                ):
                    return _MISSING

                closing = remainder.find(
                    "]"
                )

                if closing < 0:
                    return _MISSING

                index_text = remainder[
                    1:closing
                ]

                try:
                    index = int(
                        index_text
                    )
                except ValueError:
                    return _MISSING

                if not isinstance(
                    current,
                    (list, tuple),
                ):
                    return _MISSING

                if index >= len(
                    current
                ):
                    return _MISSING

                current = current[
                    index
                ]

                remainder = remainder[
                    closing + 1:
                ]

            continue

        if not isinstance(
            current,
            Mapping,
        ):
            return _MISSING

        current = current.get(
            part,
            _MISSING,
        )

        if current is _MISSING:
            return _MISSING

    return current


def _set_path(
    document: dict[str, Any],
    path: str,
    value: Any,
) -> None:
    """
    Set dotted mapping paths.

    Array mutation is intentionally avoided during merge because
    list-level three-way merge is safer than attempting destructive
    index-by-index mutation.
    """
    if not path:
        return

    if "[" in path:
        root = path.split(
            "[",
            1,
        )[0]

        if "." in root:
            return

        document[root] = deepcopy(
            value
        )
        return

    parts = path.split(
        "."
    )

    current = document

    for part in parts[:-1]:
        existing = current.get(
            part
        )

        if not isinstance(
            existing,
            dict,
        ):
            existing = {}
            current[part] = existing

        current = existing

    current[parts[-1]] = deepcopy(
        value
    )


# =========================================================
# THREE-WAY MERGE
# =========================================================

def _merge_non_conflicting(
    local: Mapping[str, Any],
    cloud: Mapping[str, Any],
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Merge local/cloud changes that do not overlap.

    When a nested list changes on both sides, it is considered one
    logical field and therefore becomes a conflict rather than being
    merged by index.
    """
    local_changed = changed_fields(
        base,
        local,
    )

    cloud_changed = changed_fields(
        base,
        cloud,
    )

    merged = deepcopy(
        comparable_record(
            base
        )
    )

    # Apply local changes.
    for field in sorted(
        local_changed
    ):
        value = _get_path(
            comparable_record(
                local
            ),
            field,
        )

        if value is _MISSING:
            continue

        _set_path(
            merged,
            field,
            value,
        )

    # Apply cloud changes.
    for field in sorted(
        cloud_changed
    ):
        value = _get_path(
            comparable_record(
                cloud
            ),
            field,
        )

        if value is _MISSING:
            continue

        _set_path(
            merged,
            field,
            value,
        )

    return merged


def three_way_merge(
    local: Mapping[str, Any],
    cloud: Mapping[str, Any],
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Perform a safe three-way merge.

    Raises ValueError when overlapping modifications exist.
    """
    local_doc = _as_mapping(
        local
    )

    cloud_doc = _as_mapping(
        cloud
    )

    base_doc = _as_mapping(
        base
    )

    local_changed = changed_fields(
        base_doc,
        local_doc,
    )

    cloud_changed = changed_fields(
        base_doc,
        cloud_doc,
    )

    overlap = (
        local_changed
        & cloud_changed
    )

    if overlap:
        raise ValueError(
            "Records contain overlapping changes: "
            + ", ".join(
                sorted(overlap)
            )
        )

    return _merge_non_conflicting(
        local_doc,
        cloud_doc,
        base_doc,
    )


# =========================================================
# CONFLICT RESULT FACTORY
# =========================================================

def _result(
    status: str,
    *,
    record: Any = None,
    fields: Optional[set[str]] = None,
    local_changed: Optional[set[str]] = None,
    cloud_changed: Optional[set[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
    }

    if record is not None:
        result["record"] = deepcopy(
            record
        )

    if fields is not None:
        result["fields"] = sorted(
            fields
        )

    if local_changed is not None:
        result["local_changed"] = sorted(
            local_changed
        )

    if cloud_changed is not None:
        result["cloud_changed"] = sorted(
            cloud_changed
        )

    if metadata:
        result["metadata"] = deepcopy(
            dict(metadata)
        )

    return result


# =========================================================
# MAIN COMPARISON
# =========================================================

def compare(
    local: Mapping[str, Any] | None,
    cloud: Mapping[str, Any] | None,
    base: Mapping[str, Any] | None = None,
    *,
    entity_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Compare local/cloud records.

    Compatible with the original API:

        compare(local, cloud)
        compare(local, cloud, base)

    Returns statuses such as:

        new_local
        new_cloud
        identical
        local_newer
        cloud_newer
        merged
        conflict
        local_deleted
        cloud_deleted
        delete_conflict
    """
    local_exists = (
        isinstance(
            local,
            Mapping,
        )
        and bool(local)
    )

    cloud_exists = (
        isinstance(
            cloud,
            Mapping,
        )
        and bool(cloud)
    )

    local_doc = _as_mapping(
        local
    )

    cloud_doc = _as_mapping(
        cloud
    )

    base_doc = _as_mapping(
        base
    )

    if entity_type:
        # Validate but do not mutate the caller's records.
        canonical_entity_type(
            entity_type
        )

    # -----------------------------------------------------
    # BRAND-NEW RECORDS
    # -----------------------------------------------------

    if not local_exists and not cloud_exists:
        return _result(
            "identical",
            record={},
        )

    if not local_exists:
        return _result(
            "new_cloud",
            record=cloud_doc,
        )

    if not cloud_exists:
        return _result(
            "new_local",
            record=local_doc,
        )

    # -----------------------------------------------------
    # DELETE / TOMBSTONE ANALYSIS
    # -----------------------------------------------------

    local_deleted = is_deleted_record(
        local_doc
    )

    cloud_deleted = is_deleted_record(
        cloud_doc
    )

    if local_deleted and cloud_deleted:
        if _same(
            comparable_record(
                local_doc
            ),
            comparable_record(
                cloud_doc
            ),
        ):
            return _result(
                "identical",
                record=cloud_doc,
            )

        stamp_comparison = compare_stamps(
            local_doc,
            cloud_doc,
        )

        if stamp_comparison > 0:
            return _result(
                "local_deleted",
                record=local_doc,
            )

        if stamp_comparison < 0:
            return _result(
                "cloud_deleted",
                record=cloud_doc,
            )

        return _result(
            "delete_conflict",
            fields=changed_fields(
                cloud_doc,
                local_doc,
            ),
        )

    if local_deleted != cloud_deleted:
        if base_doc:
            base_deleted = is_deleted_record(
                base_doc
            )

            # Local deleted, cloud unchanged from base:
            # deletion is safe.
            if (
                local_deleted
                and not base_deleted
                and _same(
                    comparable_record(
                        cloud_doc
                    ),
                    comparable_record(
                        base_doc
                    ),
                )
            ):
                return _result(
                    "local_deleted",
                    record=local_doc,
                )

            # Cloud deleted, local unchanged from base:
            # deletion is safe.
            if (
                cloud_deleted
                and not base_deleted
                and _same(
                    comparable_record(
                        local_doc
                    ),
                    comparable_record(
                        base_doc
                    ),
                )
            ):
                return _result(
                    "cloud_deleted",
                    record=cloud_doc,
                )

            # Both sides diverged from a non-deleted base.
            return _result(
                "delete_conflict",
                fields={
                    "__record_deleted__"
                },
                local_changed={
                    "__record_deleted__"
                }
                if local_deleted != base_deleted
                else set(),
                cloud_changed={
                    "__record_deleted__"
                }
                if cloud_deleted != base_deleted
                else set(),
            )

        # No base: use the explicit version/timestamp.
        stamp_comparison = compare_stamps(
            local_doc,
            cloud_doc,
        )

        if stamp_comparison > 0:
            return _result(
                "local_deleted",
                record=local_doc,
            )

        if stamp_comparison < 0:
            return _result(
                "cloud_deleted",
                record=cloud_doc,
            )

        return _result(
            "delete_conflict",
            fields={
                "__record_deleted__"
            },
        )

    # -----------------------------------------------------
    # EXACTLY IDENTICAL
    # -----------------------------------------------------

    if _same(
        comparable_record(
            local_doc
        ),
        comparable_record(
            cloud_doc
        ),
    ):
        return _result(
            "identical",
            record=cloud_doc,
        )

    # -----------------------------------------------------
    # THREE-WAY MERGE
    # -----------------------------------------------------

    if base_doc:
        local_changed = changed_fields(
            base_doc,
            local_doc,
        )

        cloud_changed = changed_fields(
            base_doc,
            cloud_doc,
        )

        overlap = (
            local_changed
            & cloud_changed
        )

        # No overlapping modifications:
        # safely merge both sides.
        if not overlap:
            merged = _merge_non_conflicting(
                local_doc,
                cloud_doc,
                base_doc,
            )

            return _result(
                "merged",
                record=merged,
                fields=set(),
                local_changed=local_changed,
                cloud_changed=cloud_changed,
            )

        # Overlap exists. Check whether overlapping values are
        # actually identical.
        true_conflicts: set[str] = set()

        local_comparable = comparable_record(
            local_doc
        )

        cloud_comparable = comparable_record(
            cloud_doc
        )

        for field in overlap:
            local_value = _get_path(
                local_comparable,
                field,
            )

            cloud_value = _get_path(
                cloud_comparable,
                field,
            )

            if not _same(
                local_value,
                cloud_value,
            ):
                true_conflicts.add(
                    field
                )

        # Same value on both sides means no real conflict.
        if not true_conflicts:
            merged = _merge_non_conflicting(
                local_doc,
                cloud_doc,
                base_doc,
            )

            return _result(
                "merged",
                record=merged,
                fields=set(),
                local_changed=local_changed,
                cloud_changed=cloud_changed,
            )

        return _result(
            "conflict",
            fields=true_conflicts,
            local_changed=local_changed,
            cloud_changed=cloud_changed,
            metadata={
                "base_present": True,
            },
        )

    # -----------------------------------------------------
    # NO BASE: VERSION / TIME ORDER
    # -----------------------------------------------------

    stamp_comparison = compare_stamps(
        local_doc,
        cloud_doc,
    )

    if stamp_comparison > 0:
        return _result(
            "local_newer",
            record=local_doc,
        )

    if stamp_comparison < 0:
        return _result(
            "cloud_newer",
            record=cloud_doc,
        )

    # -----------------------------------------------------
    # SAME TIMESTAMP + DIFFERENT PAYLOAD
    # -----------------------------------------------------

    fields = changed_fields(
        cloud_doc,
        local_doc,
    )

    return _result(
        "conflict",
        fields=fields,
        local_changed=fields,
        cloud_changed=fields,
        metadata={
            "base_present": False,
            "equal_revision_or_timestamp": True,
        },
    )


# =========================================================
# STRATEGY APPLICATION
# =========================================================

def resolve(
    decision: str,
    local: Mapping[str, Any] | None,
    cloud: Mapping[str, Any] | None,
    merged: Optional[
        Mapping[str, Any]
    ] = None,
) -> Optional[dict[str, Any]]:
    """
    Resolve a conflict according to an explicit decision.

    Supported decisions:

        keep_local
        local_wins

        keep_cloud
        cloud_wins

        merge

        manual
        None / unknown

    `manual` intentionally returns None because the caller must not
    silently choose a side for an unresolved conflict.
    """
    normalized = (
        str(
            decision or ""
        )
        .strip()
        .lower()
    )

    local_doc = _as_mapping(
        local
    )

    cloud_doc = _as_mapping(
        cloud
    )

    if normalized in {
        "keep_local",
        "local_wins",
    }:
        return deepcopy(
            local_doc
        )

    if normalized in {
        "keep_cloud",
        "cloud_wins",
    }:
        return deepcopy(
            cloud_doc
        )

    if normalized == "merge":
        if not isinstance(
            merged,
            Mapping,
        ):
            raise ValueError(
                "merged record is required."
            )

        return deepcopy(
            dict(merged)
        )

    if normalized in {
        "",
        "manual",
        "unresolved",
    }:
        return None

    raise ValueError(
        f"Unsupported conflict resolution decision: {decision}"
    )


# =========================================================
# POLICY RESOLUTION
# =========================================================

def resolve_by_strategy(
    strategy: str,
    local: Mapping[str, Any] | None,
    cloud: Mapping[str, Any] | None,
    *,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply a Sync policy strategy.

    Supported strategies correspond to models.py:

        manual
        cloud_wins
        local_wins
        latest_write
        base_merge
    """
    normalized = (
        str(
            strategy or "manual"
        )
        .strip()
        .lower()
    )

    if normalized == "manual":
        return {
            "resolved": False,
            "record": None,
            "decision": "manual",
        }

    if normalized == "cloud_wins":
        return {
            "resolved": True,
            "record": deepcopy(
                _as_mapping(cloud)
            ),
            "decision": "keep_cloud",
        }

    if normalized == "local_wins":
        return {
            "resolved": True,
            "record": deepcopy(
                _as_mapping(local)
            ),
            "decision": "keep_local",
        }

    if normalized == "latest_write":
        local_doc = _as_mapping(
            local
        )

        cloud_doc = _as_mapping(
            cloud
        )

        comparison = compare_stamps(
            local_doc,
            cloud_doc,
        )

        if comparison > 0:
            return {
                "resolved": True,
                "record": deepcopy(
                    local_doc
                ),
                "decision": "keep_local",
            }

        if comparison < 0:
            return {
                "resolved": True,
                "record": deepcopy(
                    cloud_doc
                ),
                "decision": "keep_cloud",
            }

        # Equal stamps must not silently select a side.
        return {
            "resolved": False,
            "record": None,
            "decision": "manual",
        }

    if normalized == "base_merge":
        if not base:
            return {
                "resolved": False,
                "record": None,
                "decision": "manual",
                "reason": "base_record_required",
            }

        comparison = compare(
            local,
            cloud,
            base,
        )

        if comparison.get(
            "status"
        ) == "merged":
            return {
                "resolved": True,
                "record": comparison.get(
                    "record"
                ),
                "decision": "merge",
            }

        return {
            "resolved": False,
            "record": None,
            "decision": "manual",
            "reason": "overlapping_changes",
            "fields": comparison.get(
                "fields",
                [],
            ),
        }

    raise ValueError(
        f"Unsupported synchronization conflict strategy: {strategy}"
    )


# =========================================================
# CONFLICT DETAILS
# =========================================================

def conflict_details(
    local: Mapping[str, Any] | None,
    cloud: Mapping[str, Any] | None,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Produce structured diagnostics suitable for the sync conflict
    collection and admin UI.
    """
    local_doc = _as_mapping(
        local
    )

    cloud_doc = _as_mapping(
        cloud
    )

    base_doc = _as_mapping(
        base
    )

    result = compare(
        local_doc,
        cloud_doc,
        base_doc or None,
    )

    return {
        "status": result.get(
            "status"
        ),
        "fields": result.get(
            "fields",
            [],
        ),
        "local_changed": result.get(
            "local_changed",
            [],
        ),
        "cloud_changed": result.get(
            "cloud_changed",
            [],
        ),
        "local_deleted": is_deleted_record(
            local_doc
        ),
        "cloud_deleted": is_deleted_record(
            cloud_doc
        ),
        "local_revision": _revision(
            local_doc
        ),
        "cloud_revision": _revision(
            cloud_doc
        ),
        "base_revision": _revision(
            base_doc
        )
        if base_doc
        else None,
        "local_updated_at": record_updated_at(
            local_doc
        ),
        "cloud_updated_at": record_updated_at(
            cloud_doc
        ),
        "base_updated_at": record_updated_at(
            base_doc
        )
        if base_doc
        else None,
    }