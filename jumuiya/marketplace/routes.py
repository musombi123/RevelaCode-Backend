from flask import Blueprint,request
from jumuiya.core.permissions import require_authenticated,current_user_id
from jumuiya.core.responses import ok,created
from jumuiya.core.errors import APIError
from jumuiya.marketplace import services

marketplace_bp=Blueprint("jumuiya_marketplace",__name__)

def body():
    d=request.get_json(silent=True)
    if not isinstance(d,dict):raise APIError("JSON request body is required.",400,"invalid_json")
    return d

def text(d,k,required=False):
    v=d.get(k,"")
    if not isinstance(v,str):raise APIError(f"{k} must be text.",422,"validation_error")
    v=v.strip()
    if required and not v:raise APIError(f"{k} is required.",422,"validation_error")
    return v

def num(d,k,default=0):
    try:return float(d.get(k,default))
    except (TypeError,ValueError):raise APIError(f"{k} must be a number.",422,"validation_error")

@marketplace_bp.get("/listings")
@require_authenticated
def get_listings():return ok(services.listings(current_user_id(),request.args.get("hub"),request.args.get("category")))

@marketplace_bp.post("/listings")
@require_authenticated
def add_listing():
    d=body(); payload={"title":text(d,"title",True),"description":text(d,"description"),"category":text(d,"category") or "general","hub":text(d,"hub") or "community","price":num(d,"price"),"currency":text(d,"currency") or "KES","unit":text(d,"unit") or "piece","quantity_available":num(d,"quantity_available",1),"location":text(d,"location")}
    if payload["price"]<0 or payload["quantity_available"]<0:raise APIError("price and quantity cannot be negative.",422,"validation_error")
    return created(services.create_listing(current_user_id(),payload),"Marketplace listing created.")

@marketplace_bp.delete("/listings/<listing_id>")
@require_authenticated
def remove_listing(listing_id):return ok(services.delete_listing(current_user_id(),listing_id),"Listing removed.")
