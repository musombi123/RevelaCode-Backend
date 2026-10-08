# backend/jumuiya/elimu/sync/services.py
from __future__ import annotations
from datetime import datetime,timezone
from bson import ObjectId
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize
from .models import CONNECTIONS,JOBS,RECORDS,CONFLICTS,connection_doc,job_doc
from .engine import reconcile
from .conflict import resolve

def sid(m):return str(m["school_id"])
def ser(d):
    if not d:return None
    x=dict(d)
    if isinstance(x.get("_id"),ObjectId):x["_id"]=str(x["_id"])
    for k in ("created_at","updated_at","last_sync_at","started_at","finished_at"): 
        if hasattr(x.get(k),"isoformat"):x[k]=x[k].isoformat()
    return x

def create_connection(user_id,payload):
    m=authorize(user_id,"sync.import"); doc=connection_doc(sid(m),payload["name"],payload["platform"],user_id,payload.get("metadata")); r=collection(CONNECTIONS).insert_one(doc); doc["_id"]=r.inserted_id; return ser(doc)
def list_connections(user_id):
    m=authorize(user_id,"sync.view"); return {"connections":[ser(x) for x in collection(CONNECTIONS).find({"school_id":sid(m)}).sort("created_at",-1)]}
def ingest(user_id,payload):
    m=authorize(user_id,"sync.import"); result=reconcile(sid(m),payload["entity_type"],payload["records"]); collection(CONNECTIONS).update_many({"school_id":sid(m)},{"$set":{"last_sync_at":datetime.now(timezone.utc),"status":"active","updated_at":datetime.now(timezone.utc)}}); return result
def conflicts(user_id,status="open"):
    m=authorize(user_id,"sync.resolve"); return {"conflicts":[ser(x) for x in collection(CONFLICTS).find({"school_id":sid(m),"status":status}).sort("created_at",-1)]}
def resolve_conflict(user_id,conflict_id,payload):
    m=authorize(user_id,"sync.resolve"); c=collection(CONFLICTS).find_one({"_id":ObjectId(conflict_id),"school_id":sid(m),"status":"open"})
    if not c:raise APIError("Sync conflict not found.",404,"sync_conflict_not_found")
    merged=resolve(payload["decision"],c.get("local_record"),c.get("cloud_record"),payload.get("merged_record"))
    if merged is not None:
        collection(RECORDS).update_one({"school_id":sid(m),"entity_type":c["entity_type"],"entity_key":c["entity_key"]},{"$set":{"record":merged}},{"upsert":True})
    collection(CONFLICTS).update_one({"_id":c["_id"]},{"$set":{"status":"resolved","resolution":payload,"resolved_by":str(user_id),"resolved_at":datetime.now(timezone.utc),"updated_at":datetime.now(timezone.utc)}})
    return {"resolved":True,"conflict_id":str(conflict_id),"decision":payload["decision"]}

def export_records(user_id,entity_type):
    m=authorize(user_id,"sync.export"); rows=collection(RECORDS).find({"school_id":sid(m),"entity_type":entity_type}); return [ser(x.get("record") or {}) for x in rows]
