"""Dependency-free request timing and correlation metadata."""
from __future__ import annotations

import logging
import time
from uuid import uuid4


_REQUEST_ID_KEY = "revelacode.request_id"
_REQUEST_STARTED_KEY = "revelacode.request_started_at"


def begin_request(environ: dict, *, clock=time.perf_counter) -> str:
    """Create a server-generated request identifier and start timestamp."""
    request_id = uuid4().hex
    environ[_REQUEST_ID_KEY] = request_id
    environ[_REQUEST_STARTED_KEY] = clock()
    return request_id


def apply_request_metrics(
    response,
    environ: dict,
    *,
    method: str,
    path: str,
    logger: logging.Logger,
    slow_threshold_ms: float = 1000.0,
    clock=time.perf_counter,
):
    """Attach timing headers and log slow requests without logging user data."""
    request_id = str(environ.get(_REQUEST_ID_KEY) or uuid4().hex)
    started_at = environ.get(_REQUEST_STARTED_KEY)
    if started_at is None:
        elapsed_ms = 0.0
    else:
        try:
            elapsed_ms = max(0.0, (clock() - float(started_at)) * 1000.0)
        except (TypeError, ValueError):
            elapsed_ms = 0.0

    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("Server-Timing", f"app;dur={elapsed_ms:.2f}")

    if elapsed_ms >= max(0.0, float(slow_threshold_ms)):
        logger.warning(
            "slow_api_request request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
            request_id,
            str(method or "")[:12],
            str(path or "")[:240],
            getattr(response, "status_code", "unknown"),
            elapsed_ms,
        )
    return response
