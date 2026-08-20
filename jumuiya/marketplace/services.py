from bson import ObjectId
from bson.errors import InvalidId
from jumuiya.core.database import collection
from jumuiya.core.errors import APIError
from jumuiya.core.audit import log_action
from jumuiya.marketplace.models import listing_document

def cid(v):
    try:return ObjectId(v)
    except (InvalidId,TypeError):return v

def ser(doc):
    if not doc:return None
    o=dict(doc)
    if "_id" in o:o["id"]=str(o.pop("_id"))
    for k,v in list(o.items()):
        if isinstance(v,ObjectId):o[k]=str(v)
        elif hasattr(v,"isoformat"):o[k]=v.isoformat()
    return o

def listings(user_id=None,hub=None,category=None):
    q={"status":"active"}
    if hub:q["hub"]=hub
    if category:q["category"]=category
    return [ser(x) for x in collection("jumuiya_marketplace_listings").find(q).sort("created_at",-1)]

def create_listing(user_id,data):
    doc=listing_document(user_id,data); r=collection("jumuiya_marketplace_listings").insert_one(doc); doc["_id"]=r.inserted_id; log_action(user_id,"marketplace.listing.created","listing",r.inserted_id); return ser(doc)

def delete_listing(user_id,listing_id):
    r=collection("jumuiya_marketplace_listings").update_one({"_id":cid(listing_id),"seller_user_id":str(user_id)},{"$set":{"status":"deleted"}})
    if r.modified_count!=1:raise APIError("Listing not found or not owned by you.",404,"listing_not_found")
    return {"deleted":True,"id":str(listing_id)}
