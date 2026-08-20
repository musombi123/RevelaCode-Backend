from flask import Blueprint,request
from jumuiya.core.permissions import require_authenticated,current_user,current_user_id
from jumuiya.core.responses import ok
from jumuiya.identity import services

identity_bp=Blueprint("jumuiya_identity",__name__)

@identity_bp.get("/me")
@require_authenticated
def me():return ok({"account":current_user(),"profile":services.profile(current_user())})

@identity_bp.put("/profile")
@require_authenticated
def update_profile():return ok(services.update_profile(current_user_id(),request.get_json(silent=True) or {}),"Profile updated.")
