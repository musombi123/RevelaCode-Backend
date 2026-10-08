# backend/jumuiya/elimu/sync/schemas.py
from __future__ import annotations

def _s(v):return str(v).strip() if v is not None else ""
def connection_payload(d):
    if not isinstance(d,dict):raise ValueError("JSON object is required.")
    return {"name":_s(d.get("name")) or "School Desktop","platform":_s(d.get("platform") or "windows"),"metadata":d.get("metadata") or {}}
def records_payload(d):
    if not isinstance(d,dict):raise ValueError("JSON object is required.")
    entity_type=_s(d.get("entity_type")); records=d.get("records")
    if not entity_type or not isinstance(records,list):raise ValueError("entity_type and records are required.")
    return {"entity_type":entity_type,"records":[x for x in records if isinstance(x,dict)],"connection_token":_s(d.get("connection_token")) or None}
def conflict_resolution_payload(d):
    if not isinstance(d,dict):raise ValueError("JSON object is required.")
    decision=_s(d.get("decision")).lower()
    if decision not in {"keep_local","keep_cloud","merge","manual"}:raise ValueError("Invalid conflict decision.")
    return {"decision":decision,"merged_record":d.get("merged_record") if isinstance(d.get("merged_record"),dict) else None}
