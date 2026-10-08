# backend/jumuiya/elimu/automation/jobs.py
from __future__ import annotations
from datetime import datetime,timezone
from backend.jumuiya.core.database import collection
from .services import RULES

def now():return datetime.now(timezone.utc)
def due_rules(school_id):
    return list(collection(RULES).find({"school_id":str(school_id),"enabled":True}))
def run_due_jobs(school_id,context=None):
    rules=due_rules(school_id); results=[]
    for rule in rules:
        results.append({"rule_id":str(rule.get("_id")),"name":rule.get("name"),"trigger":rule.get("trigger"),"action":rule.get("action"),"status":"ready"})
    return {"generated_at":now().isoformat(),"count":len(results),"jobs":results}

def daily_school_jobs(school_id):
    return run_due_jobs(school_id,{"schedule":"daily"})
