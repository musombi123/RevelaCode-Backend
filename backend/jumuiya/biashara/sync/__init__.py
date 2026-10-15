"""Durable synchronization primitives for Biashara OS.

Provider adapters can build on this module. No external provider is marked
connected or delivered until a real adapter verifies that result.
"""

from backend.jumuiya.biashara.sync.outbox import (
    build_outbox_manifest,
    dispatch_manifest_for_record,
    enqueue_outbox_event,
    repair_outbox_manifests,
)

__all__ = [
    "build_outbox_manifest",
    "dispatch_manifest_for_record",
    "enqueue_outbox_event",
    "repair_outbox_manifests",
]
