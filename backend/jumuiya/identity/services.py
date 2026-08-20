from pymongo import ReturnDocument
from jumuiya.core.database import collection
from jumuiya.core.audit import log_action
from jumuiya.identity.models import profile_document

def profile(user):
    c=collection("jumuiya_profiles"); doc=c.find_one({"user_id":str(user["id"])})
    if doc:return _ser(doc)
    p=profile_document(user); r=c.insert_one(p); p["_id"]=r.inserted_id; return _ser(p)

def update_profile(user_id,data):
    allowed=["full_name","bio","avatar_url","county","town"]
    update={k:v.strip() if isinstance(v,str) else v for k,v in data.items() if k in allowed}
    from datetime import datetime,timezone; update["updated_at"]=datetime.now(timezone.utc)
    doc=collection("jumuiya_profiles").find_one_and_update({"user_id":str(user_id)},{"$set":update},upsert=True,return_document=ReturnDocument.AFTER)
    log_action(user_id,"identity.profile.updated","profile",doc.get("_id")); return _ser(doc)

def _ser(doc):
    out=dict(doc); out["id"]=str(out.pop("_id")) if "_id" in out else str(out.get("id"));
    for k,v in list(out.items()):
        if hasattr(v,"isoformat"):out[k]=v.isoformat()
    return out
