from flask import jsonify

class APIError(Exception):
    def __init__(self, message, status_code=400, code="bad_request"):
        self.message = message
        self.status_code = status_code
        self.code = code

def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify({
            "success": False,
            "error": {"code": error.code, "message": error.message}
        }), error.status_code
