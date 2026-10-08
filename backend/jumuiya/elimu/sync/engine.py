# backend/jumuiya/elimu/sync/engine.py
from __future__ import annotations
from backend.jumuiya.core.database import collection
from .conflict import compare
from .mapper import canonical_record,identity_key
from .models import RECORDS,CONFLICTS,conflict_doc

def reconcile(school_id,entity_type,records,base_records=None,source="desktop"):
    base_records=base_records or {}; results={"created":0,"updated":0,"unchanged":0,"conflicts":0,"items":[]}
    target=collection(RECORDS)
    for raw in records:
        local=canonical_record(entity_type,raw,source); key=identity_key(entity_type,local)
        cloud_doc=target.find_one({"school_id":str(school_id),"entity_type":entity_type,"entity_key":key})
        cloud=cloud_doc.get("record") if cloud_doc else None
        base=base_records.get(key) if isinstance(base_records,dict) else None
        decision=compare(local,cloud,base)
        status=decision["status"]
        if status in {"new_local","local_newer","merged"}:
            target.update_one({"school_id":str(school_id),"entity_type":entity_type,"entity_key":key},{"$set":{"school_id":str(school_id),"entity_type":entity_type,"entity_key":key,"record":decision["record"]}},{"upsert":True})
            results["created" if status=="new_local" else "updated"]+=1
        elif status in {"identical","cloud_newer"}:results["unchanged"]+=1
        elif status=="conflict":
            collection(CONFLICTS).insert_one(conflict_doc(school_id,entity_type,key,local,cloud,base,{"source":source,"fields":decision.get("fields",[])})); results["conflicts"]+=1
        results["items"].append({"entity_key":key,"status":status})
    return results
