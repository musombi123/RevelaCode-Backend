from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from jumuiya.core.database import collection
from jumuiya.core.errors import APIError
from jumuiya.core.audit import log_action
from jumuiya.community.models import post_document

def cid(value):
    try:return ObjectId(value)
    except (InvalidId,TypeError):return value

def serialise(doc):
    if not doc:return None
    out=dict(doc)
    if "_id" in out:out["id"]=str(out.pop("_id"))
    for k,v in list(out.items()):
        if isinstance(v,ObjectId):out[k]=str(v)
        elif hasattr(v,"isoformat"):out[k]=v.isoformat()
    return out

def create_post(user_id,data):
    doc=post_document(user_id,data); r=collection("jumuiya_community_posts").insert_one(doc); doc["_id"]=r.inserted_id
    log_action(user_id,"community.post.created","community_post",r.inserted_id); return serialise(doc)

def feed(category=None,hub=None,limit=30):
    q={"status":"published"}
    if category:q["category"]=category
    if hub:q["hub"]=hub
    return [serialise(x) for x in collection("jumuiya_community_posts").find(q).sort("created_at",-1).limit(limit)]

def update_post(user_id,post_id,data):
    allowed=["title","body","category","hub","location"]
    update={k:data[k] for k in allowed if k in data}
    from datetime import datetime,timezone; update["updated_at"]=datetime.now(timezone.utc)
    doc=collection("jumuiya_community_posts").find_one_and_update({"_id":cid(post_id),"author_user_id":str(user_id)},{"$set":update},return_document=ReturnDocument.AFTER)
    if not doc:raise APIError("Post not found or not owned by you.",404,"post_not_found")
    return serialise(doc)

def delete_post(user_id,post_id):
    result=collection("jumuiya_community_posts").delete_one({"_id":cid(post_id),"author_user_id":str(user_id)})
    if result.deleted_count!=1:raise APIError("Post not found or not owned by you.",404,"post_not_found")
    log_action(user_id,"community.post.deleted","community_post",post_id); return {"deleted":True,"id":str(post_id)}

def add_comment(user_id,post_id,body):
    post=collection("jumuiya_community_posts").find_one({"_id":cid(post_id),"status":"published"})
    if not post:raise APIError("Post not found.",404,"post_not_found")
    from datetime import datetime,timezone
    doc={"post_id":str(post["_id"]),"author_user_id":str(user_id),"body":body,"created_at":datetime.now(timezone.utc)}
    r=collection("jumuiya_community_comments").insert_one(doc)
    collection("jumuiya_community_posts").update_one({"_id":post["_id"]},{"$inc":{"comments_count":1}})
    doc["_id"]=r.inserted_id; return serialise(doc)

def comments(post_id):
    return [serialise(x) for x in collection("jumuiya_community_comments").find({"post_id":str(post_id)}).sort("created_at",1)]

def react(user_id,post_id):
    pid=str(post_id); reactions=collection("jumuiya_community_reactions"); existing=reactions.find_one({"post_id":pid,"user_id":str(user_id)})
    if existing:
        reactions.delete_one({"_id":existing["_id"]}); collection("jumuiya_community_posts").update_one({"_id":cid(post_id)},{"$inc":{"likes_count":-1}}); liked=False
    else:
        from datetime import datetime,timezone; reactions.insert_one({"post_id":pid,"user_id":str(user_id),"created_at":datetime.now(timezone.utc)}); collection("jumuiya_community_posts").update_one({"_id":cid(post_id)},{"$inc":{"likes_count":1}}); liked=True
    post=collection("jumuiya_community_posts").find_one({"_id":cid(post_id)})
    return {"liked":liked,"likes_count":post.get("likes_count",0) if post else 0}
