from flask import Blueprint,request
from jumuiya.core.permissions import require_authenticated,current_user_id
from jumuiya.core.responses import ok,created
from jumuiya.core.errors import APIError
from jumuiya.community import services

community_bp=Blueprint("jumuiya_community",__name__)

def body():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):raise APIError("JSON request body is required.",400,"invalid_json")
    return data

def text(data,key,required=True,max_len=5000):
    val=data.get(key,"")
    if not isinstance(val,str):raise APIError(f"{key} must be text.",422,"validation_error")
    val=val.strip()
    if required and not val:raise APIError(f"{key} is required.",422,"validation_error")
    if len(val)>max_len:raise APIError(f"{key} is too long.",422,"validation_error")
    return val

@community_bp.get("/feed")
@require_authenticated
def get_feed():
    try:limit=min(max(int(request.args.get("limit",30)),1),100)
    except ValueError:limit=30
    return ok(services.feed(request.args.get("category"),request.args.get("hub"),limit))

@community_bp.post("/posts")
@require_authenticated
def create_post():
    data=body(); payload={"title":text(data,"title",True,180),"body":text(data,"body",True,10000),"category":text(data,"category",False,60) or "general","hub":text(data,"hub",False,60) or "community","location":text(data,"location",False,160)}
    return created(services.create_post(current_user_id(),payload),"Community post published.")

@community_bp.put("/posts/<post_id>")
@require_authenticated
def edit_post(post_id):return ok(services.update_post(current_user_id(),post_id,body()),"Post updated.")

@community_bp.delete("/posts/<post_id>")
@require_authenticated
def remove_post(post_id):return ok(services.delete_post(current_user_id(),post_id),"Post deleted.")

@community_bp.get("/posts/<post_id>/comments")
@require_authenticated
def get_comments(post_id):return ok(services.comments(post_id))

@community_bp.post("/posts/<post_id>/comments")
@require_authenticated
def add_comment(post_id):
    text_value=text(body(),"body",True,3000); return created(services.add_comment(current_user_id(),post_id,text_value),"Comment added.")

@community_bp.post("/posts/<post_id>/react")
@require_authenticated
def react(post_id):return ok(services.react(current_user_id(),post_id))
