import re
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from jumuiya.core.database import collection
from jumuiya.core.errors import APIError
from jumuiya.core.audit import log_action
from jumuiya.biashara.models import business_document, product_document, customer_document, order_document, expense_document

def clean_id(value):
    try: return ObjectId(value)
    except (InvalidId, TypeError): return value

def serialise(doc):
    if not doc: return None
    out=dict(doc)
    if "_id" in out: out["id"]=str(out.pop("_id"))
    for key,val in list(out.items()):
        if isinstance(val,ObjectId): out[key]=str(val)
        elif hasattr(val,"isoformat"): out[key]=val.isoformat()
    return out

def serialise_many(docs): return [serialise(d) for d in docs]

def slugify(value):
    value=re.sub(r"[^a-zA-Z0-9\s-]","",value.lower()); return re.sub(r"[\s_-]+","-",value).strip("-") or "business"

def unique_slug(name, current_id=None):
    base=slugify(name); slug=base; n=2; c=collection("jumuiya_businesses")
    while True:
        q={"slug":slug}
        if current_id: q["_id"]={"$ne":current_id}
        if not c.find_one(q): return slug
        slug=f"{base}-{n}"; n+=1

def get_business_for_user(user_id): return serialise(collection("jumuiya_businesses").find_one({"owner_user_id":str(user_id)}))

def _require_business(user_id):
    b=get_business_for_user(user_id)
    if not b: raise APIError("Create your business profile first.",409,"business_required")
    return b

def create_or_update_business(user_id,p):
    c=collection("jumuiya_businesses"); old=c.find_one({"owner_user_id":str(user_id)})
    if old:
        fields=["name","description","phone","email","location","county","category","logo_url"]
        update={k:p.get(k,"") for k in fields}; update["slug"]=unique_slug(p["name"],old["_id"])
        from datetime import datetime,timezone; update["updated_at"]=datetime.now(timezone.utc)
        doc=c.find_one_and_update({"_id":old["_id"]},{"$set":update},return_document=ReturnDocument.AFTER)
        log_action(user_id,"business.updated","business",doc["_id"]); return serialise(doc)
    doc=business_document(user_id,p,unique_slug(p["name"])); r=c.insert_one(doc); doc["_id"]=r.inserted_id
    log_action(user_id,"business.created","business",r.inserted_id); return serialise(doc)

def create_product(user_id,p):
    b=_require_business(user_id); doc=product_document(b["id"],p); r=collection("jumuiya_products").insert_one(doc); doc["_id"]=r.inserted_id
    log_action(user_id,"product.created","product",r.inserted_id); return serialise(doc)

def list_products(user_id,status=None):
    b=_require_business(user_id); q={"business_id":b["id"]};
    if status: q["status"]=status
    return serialise_many(collection("jumuiya_products").find(q).sort("created_at",-1))

def update_product(user_id,product_id,p):
    b=_require_business(user_id); allowed=["name","description","category","sku","price","currency","stock_quantity","unit","image_url","status"]; update={k:p[k] for k in allowed if k in p}
    doc=collection("jumuiya_products").find_one_and_update({"_id":clean_id(product_id),"business_id":b["id"]},{"$set":update},return_document=ReturnDocument.AFTER)
    if not doc: raise APIError("Product not found.",404,"product_not_found")
    log_action(user_id,"product.updated","product",doc["_id"]); return serialise(doc)

def create_customer(user_id,p):
    b=_require_business(user_id); doc=customer_document(b["id"],p); r=collection("jumuiya_customers").insert_one(doc); doc["_id"]=r.inserted_id; log_action(user_id,"customer.created","customer",r.inserted_id); return serialise(doc)

def list_customers(user_id):
    b=_require_business(user_id); return serialise_many(collection("jumuiya_customers").find({"business_id":b["id"]}).sort("created_at",-1))

def create_order(user_id,p):
    b=_require_business(user_id); doc=order_document(b["id"],p); r=collection("jumuiya_orders").insert_one(doc); doc["_id"]=r.inserted_id; log_action(user_id,"order.created","order",r.inserted_id); return serialise(doc)

def list_orders(user_id,status=None):
    b=_require_business(user_id); q={"business_id":b["id"]};
    if status: q["status"]=status
    return serialise_many(collection("jumuiya_orders").find(q).sort("created_at",-1))

def create_expense(user_id,p):
    b=_require_business(user_id); doc=expense_document(b["id"],p); r=collection("jumuiya_expenses").insert_one(doc); doc["_id"]=r.inserted_id; log_action(user_id,"expense.created","expense",r.inserted_id); return serialise(doc)

def dashboard(user_id):
    b=_require_business(user_id); bid=b["id"]; products=collection("jumuiya_products"); orders=collection("jumuiya_orders"); sales=collection("jumuiya_sales"); expenses=collection("jumuiya_expenses"); customers=collection("jumuiya_customers")
    sa=list(sales.aggregate([{"$match":{"business_id":bid}},{"$group":{"_id":None,"total":{"$sum":"$amount"}}}])); ea=list(expenses.aggregate([{"$match":{"business_id":bid}},{"$group":{"_id":None,"total":{"$sum":"$amount"}}}]))
    total_sales=float(sa[0]["total"]) if sa else 0.0; total_expenses=float(ea[0]["total"]) if ea else 0.0
    return {"business":b,"metrics":{"products":products.count_documents({"business_id":bid,"status":{"$ne":"deleted"}}),"low_stock":products.count_documents({"business_id":bid,"status":"active","stock_quantity":{"$lte":5}}),"customers":customers.count_documents({"business_id":bid}),"pending_orders":orders.count_documents({"business_id":bid,"status":{"$in":["pending","confirmed","processing"]}}),"sales_total":total_sales,"expenses_total":total_expenses,"net_estimate":total_sales-total_expenses}}
