# backend/jumuiya/elimu/automation/services.py
from __future__ import annotations
from datetime import datetime,timezone
from backend.jumuiya.core.database import collection
from backend.jumuiya.elimu.permissions import authorize

RULES="jumuiya_elimu_automation_rules"; LOGS="jumuiya_elimu_automation_logs"

def now():return datetime.now(timezone.utc)
def sid(m):return str(m["school_id"])
def create_rule(user_id,payload):
    m=authorize(user_id,"automation.manage"); doc={"school_id":sid(m),"name":payload["name"],"trigger":payload["trigger"],"action":payload["action"],"enabled":bool(payload.get("enabled",True)),"created_by":str(user_id),"created_at":now(),"updated_at":now()}; r=collection(RULES).insert_one(doc); doc["_id"]=str(r.inserted_id); return doc
def list_rules(user_id):
    m=authorize(user_id,"automation.view"); return {"rules":[dict(x,**({"_id":str(x["_id"])} if "_id" in x else {})) for x in collection(RULES).find({"school_id":sid(m)}).sort("created_at",-1)]}
def run_rule(user_id,rule_id,context=None):
    m=authorize(user_id,"automation.manage"); rule=collection(RULES).find_one({"school_id":sid(m),"_id":__oid(rule_id)})
    if not rule:raise ValueError("Automation rule not found.")
    log={"school_id":sid(m),"rule_id":str(rule_id),"context":context or {},"status":"simulated","created_at":now()}; collection(LOGS).insert_one(log); return {"rule_id":str(rule_id),"status":"simulated","action":rule["action"]}
def __oid(value):
    from bson import ObjectId
    try:return ObjectId(value)
    except Exception:return value
