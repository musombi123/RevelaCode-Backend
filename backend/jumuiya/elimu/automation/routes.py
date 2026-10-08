# backend/jumuiya/elimu/automation/routes.py
from __future__ import annotations
from flask import Blueprint,request
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id
from backend.jumuiya.core.responses import ok,created
from backend.jumuiya.elimu.permissions import get_membership
from . import services,jobs

automation_bp=Blueprint("jumuiya_elimu_automation",__name__,url_prefix="/automation")
def body():
    d=request.get_json(silent=True)
    if not isinstance(d,dict):raise APIError("JSON request body is required.",400,"invalid_json")
    return d

@automation_bp.get("/rules")
def rules():return ok(services.list_rules(current_user_id()))
@automation_bp.post("/rules")
def create_rule():
    d=body()
    if not str(d.get("name") or "").strip() or not d.get("trigger") or not d.get("action"):raise APIError("name, trigger and action are required.",422,"validation_error")
    return created(services.create_rule(current_user_id(),d),"Automation rule created.")
@automation_bp.post("/run")
def run():
    m=get_membership(current_user_id());
    if not m:raise APIError("Active Elimu membership is required.",403,"elimu_membership_required")
    return ok(jobs.run_due_jobs(str(m["school_id"]),body()))
