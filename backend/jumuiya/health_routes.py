from flask import Blueprint
from jumuiya.core.responses import ok

jumuiya_health_bp = Blueprint("jumuiya_health", __name__)

@jumuiya_health_bp.get("/health")
def health():
    return ok({"platform":"jumuiya","status":"online","version":"1.0.0"})
