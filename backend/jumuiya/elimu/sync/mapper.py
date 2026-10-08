# backend/jumuiya/elimu/sync/mapper.py
from __future__ import annotations
from datetime import datetime,timezone

def normalize(value):
    if isinstance(value,str):return value.strip()
    return value

def canonical_record(entity_type,record,source="desktop"):
    r={k:normalize(v) for k,v in record.items()}; r["source_system"]=source; r["sync_updated_at"]=datetime.now(timezone.utc); return r

def identity_key(entity_type,record):
    candidates={
      "student":["student_id","admission_number","external_id"],
      "student_fee":["fee_id","external_id","receipt_number"],
      "staff":["user_id","employee_number","email"],
      "class":["class_id","external_id","name"],
      "attendance":["attendance_id","external_id"],
      "assessment":["assessment_id","external_id"],
    }.get(entity_type,["id","external_id"])
    for key in candidates:
        v=record.get(key)
        if v not in (None,""):return str(v)
    raise ValueError(f"Unable to determine identity for {entity_type} record.")
