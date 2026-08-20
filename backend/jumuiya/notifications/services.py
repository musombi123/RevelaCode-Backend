from bson import ObjectId
from backend.jumuiya.core.database import collection
from backend.jumuiya.notifications.models import notification_document

def notify(user_id,data):
    doc=notification_document(user_id,data); r=collection("jumuiya_notifications").insert_one(doc); doc["_id"]=r.inserted_id; return _ser(doc)

def list_notifications(user_id,limit=30):return [_ser(x) for x in collection("jumuiya_notifications").find({"user_id":str(user_id)}).sort("created_at",-1).limit(limit)]

def mark_read(user_id,notification_id):
    try:oid=ObjectId(notification_id)
    except Exception:oid=notification_id
    collection("jumuiya_notifications").update_one({"_id":oid,"user_id":str(user_id)},{"$set":{"read":True}}); return {"id":str(notification_id),"read":True}

def _ser(doc):
    out=dict(doc); out["id"]=str(out.pop("_id")) if "_id" in out else str(out.get("id"));
    for k,v in list(out.items()):
        if hasattr(v,"isoformat"):out[k]=v.isoformat()
    return out
