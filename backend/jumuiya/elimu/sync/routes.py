# backend/jumuiya/elimu/sync/routes.py
from __future__ import annotations
from flask import Blueprint,request
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id
from backend.jumuiya.core.responses import ok,created
from . import schemas,services

sync_bp=Blueprint("jumuiya_elimu_sync",__name__,url_prefix="/sync")
def body():
    d=request.get_json(silent=True)
    if not isinstance(d,dict):raise APIError("JSON request body is required.",400,"invalid_json")
    return d
def val(fn,d):
    try:return fn(d)
    except ValueError as e:raise APIError(str(e),422,"validation_error")

@sync_bp.get("/connections")
def connections():return ok(services.list_connections(current_user_id()))
@sync_bp.post("/connections")
def create_connection():return created(services.create_connection(current_user_id(),val(schemas.connection_payload,body())),"Desktop sync connection created.")
@sync_bp.post("/ingest")
def ingest():return ok(services.ingest(current_user_id(),val(schemas.records_payload,body())))
@sync_bp.get("/conflicts")
def conflicts():return ok(services.conflicts(current_user_id(),request.args.get("status","open")))
@sync_bp.post("/conflicts/<conflict_id>/resolve")
def resolve(conflict_id):return ok(services.resolve_conflict(current_user_id(),conflict_id,val(schemas.conflict_resolution_payload,body())),"Sync conflict resolved.")
@sync_bp.get("/export/<entity_type>")
def export_entity(entity_type):return ok({"entity_type":entity_type,"records":services.export_records(current_user_id(),entity_type)})
