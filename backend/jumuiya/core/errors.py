# backend/jumuiya/core/errors.py

from __future__ import annotations

from flask import jsonify


# =========================================================
# JUMUIYA API ERROR
# =========================================================

class APIError(Exception):
    """
    Controlled application error used throughout Jumuiya.

    Example:

        raise APIError(
            "Business profile not found.",
            404,
            "business_not_found",
        )
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "bad_request",
        details=None,
    ):
        super().__init__(message)

        self.message = str(
            message
        )

        self.status_code = int(
            status_code
        )

        self.code = str(
            code
        )

        self.details = details


# =========================================================
# ERROR HANDLERS
# =========================================================

def register_error_handlers(app):
    """
    Register Jumuiya's controlled API error handlers.

    This should be called once when Jumuiya is registered
    with the existing Flask application.
    """

    @app.errorhandler(APIError)
    def handle_api_error(error):

        payload = {
            "success": False,
            "error": {
                "code": error.code,
                "message": error.message,
            },
        }

        if error.details is not None:

            payload["error"][
                "details"
            ] = error.details

        return (
            jsonify(payload),
            error.status_code,
        )