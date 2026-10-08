# backend/jumuiya/elimu/sync/queue.py
from __future__ import annotations
from datetime import datetime,timezone
from backend.jumuiya.core.database import collection
from .models import JOBS

def now():return datetime.now(timezone.utc)
def enqueue(school_id,kind,payload,created_by):
    doc={"school_id":str(school_id),"kind":kind,"payload":payload,"status":"queued","created_by":str(created_by),"created_at":now(),"updated_at":now()}; return collection(JOBS).insert_one(doc).inserted_id

def claim(school_id):
    return collection(JOBS).find_one_and_update({"school_id":str(school_id),"status":"queued"},{"$set":{"status":"running","started_at":now(),"updated_at":now()}},sort=[("created_at",1)])

def complete(job_id,result=None):collection(JOBS).update_one({"_id":job_id},{"$set":{"status":"completed","result":result or {},"finished_at":now(),"updated_at":now()}})
def fail(job_id,error):collection(JOBS).update_one({"_id":job_id},{"$set":{"status":"failed","error":str(error),"finished_at":now(),"updated_at":now()}})
