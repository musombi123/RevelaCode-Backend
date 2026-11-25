"""Tests for request correlation and slow-request timing metadata."""
import logging

from backend.observability.request_metrics import (
    apply_request_metrics,
    begin_request,
)


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.headers = {}


def test_request_id_is_server_generated_and_application_timing_is_attached():
    now = [10.0]
    environ = {}
    request_id = begin_request(environ, clock=lambda: now[0])
    now[0] += 0.025
    response = apply_request_metrics(
        FakeResponse(),
        environ,
        method="GET",
        path="/api/health",
        logger=logging.getLogger("test"),
        clock=lambda: now[0],
    )

    assert response.headers["X-Request-ID"] == request_id
    assert response.headers["Server-Timing"] == "app;dur=25.00"
    assert len(request_id) == 32


def test_slow_requests_emit_structured_warning_without_query_or_body_data(caplog):
    now = [2.0]
    environ = {}
    begin_request(environ, clock=lambda: now[0])
    now[0] += 0.5

    with caplog.at_level(logging.WARNING):
        apply_request_metrics(
            FakeResponse(503),
            environ,
            method="POST",
            path="/api/auth/login",
            logger=logging.getLogger("test.slow"),
            slow_threshold_ms=100,
            clock=lambda: now[0],
        )

    assert "slow_api_request" in caplog.text
    assert "method=POST" in caplog.text
    assert "status=503" in caplog.text
    assert "password" not in caplog.text.lower()


def test_existing_response_correlation_headers_are_preserved():
    environ = {}
    response = FakeResponse()
    response.headers["X-Request-ID"] = "upstream-id"
    response.headers["Server-Timing"] = "db;dur=4"

    result = apply_request_metrics(
        response,
        environ,
        method="GET",
        path="/",
        logger=logging.getLogger("test"),
    )

    assert result.headers["X-Request-ID"] == "upstream-id"
    assert result.headers["Server-Timing"] == "db;dur=4"
