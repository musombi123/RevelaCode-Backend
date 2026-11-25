"""Bounded, short-lived cache for verified custom-origin decisions."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable


class OriginVerificationCache:
    """Cache resolver booleans without caching resolver failures.

    This cache is a performance optimization for CORS origin verification.
    It is not an authorization/tenant-access cache: application route
    authorization must still run for every authenticated request.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 5.0,
        max_entries: int = 2048,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.ttl_seconds = max(0.0, min(float(ttl_seconds), 30.0))
        self.max_entries = max(1, min(int(max_entries), 16384))
        self._clock = clock or time.monotonic
        self._entries: OrderedDict[str, tuple[float, bool]] = OrderedDict()
        self._lock = threading.RLock()

    def get_or_resolve(
        self,
        hostname: str,
        resolver: Callable[[str], bool],
    ) -> bool:
        key = str(hostname or "").strip().lower()
        if not key:
            return False
        if self.ttl_seconds <= 0:
            return bool(resolver(key))

        now = self._clock()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                expires_at, result = cached
                if expires_at > now:
                    self._entries.move_to_end(key)
                    return result
                self._entries.pop(key, None)

        # Resolve outside the lock. Exceptions intentionally propagate and
        # are not cached, allowing the next request to recover immediately.
        result = bool(resolver(key))
        with self._lock:
            self._entries[key] = (self._clock() + self.ttl_seconds, result)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return result

    def invalidate(self, hostname: str | None = None) -> None:
        with self._lock:
            if hostname is None:
                self._entries.clear()
            else:
                self._entries.pop(str(hostname).strip().lower(), None)
