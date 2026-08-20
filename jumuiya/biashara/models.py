from datetime import datetime, timezone

def now_utc(): return datetime.now(timezone.utc)

def business_document(user_id, p, slug):
    now = now_utc()
    return {"owner_user_id": str(user_id), "name": p["name"], "slug": slug, "description": p.get("description",""), "phone": p.get("phone",""), "email": p.get("email",""), "location": p.get("location",""), "county": p.get("county",""), "category": p.get("category",""), "logo_url": p.get("logo_url",""), "status":"active", "created_at":now, "updated_at":now}

def product_document(business_id, p):
    now=now_utc(); return {"business_id":str(business_id), "name":p["name"], "description":p.get("description",""), "category":p.get("category",""), "sku":p.get("sku",""), "price":float(p.get("price",0)), "currency":p.get("currency","KES"), "stock_quantity":float(p.get("stock_quantity",0)), "unit":p.get("unit","piece"), "image_url":p.get("image_url",""), "status":p.get("status","active"), "created_at":now, "updated_at":now}

def customer_document(business_id,p):
    now=now_utc(); return {"business_id":str(business_id), "name":p["name"], "phone":p.get("phone",""), "email":p.get("email",""), "notes":p.get("notes",""), "created_at":now, "updated_at":now}

def order_document(business_id,p):
    now=now_utc(); return {"business_id":str(business_id), "customer_id":p.get("customer_id"), "items":p.get("items",[]), "total_amount":float(p.get("total_amount",0)), "currency":p.get("currency","KES"), "status":"pending", "payment_status":"unpaid", "notes":p.get("notes",""), "created_at":now, "updated_at":now}

def expense_document(business_id,p):
    return {"business_id":str(business_id), "title":p["title"], "category":p.get("category",""), "amount":float(p["amount"]), "currency":p.get("currency","KES"), "notes":p.get("notes",""), "created_at":now_utc(), "spent_at":now_utc()}
