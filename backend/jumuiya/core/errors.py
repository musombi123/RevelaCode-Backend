from __future__ import annotations

from flask import jsonify

class APIError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "bad_request", details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details

def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(error):
        payload = {"success": False, "error": {"code": error.code, "message": error.message}}
        if error.details is not None:
            payload["error"]["details"] = error.details
        return jsonify(payload), error.status_code

