"""Jumuiya OS Revenue Engine package."""

from flask import Blueprint

revenue_bp = Blueprint(
    "jumuiya_revenue",
    __name__,
    url_prefix="/api/revenue",
)

# Import modules to attach public/user routes and platform-admin routes to the
# same blueprint before main.py registers it.
from backend.revenue import routes  # noqa: E402,F401
from backend.revenue import admin_routes  # noqa: E402,F401
