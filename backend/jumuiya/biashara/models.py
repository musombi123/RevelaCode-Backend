from datetime import datetime, timezone

def now_utc():
    return datetime.now(timezone.utc)

def business_document(user_id, p, slug):
    return {
        "owner_user_id": str(user_id),
        "name": p["name"].strip(),
        "slug": slug,
        "description": p.get("description", "").strip(),
        "phone": p.get("phone", "").strip(),
        "email": p.get("email", "").strip(),
        "location": p.get("location", "").strip(),
        "county": p.get("county", "").strip(),
        "category": p.get("category", "").strip(),
        "logo_url": p.get("logo_url", "").strip(),
        "status": "active",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }

def product_document(business_id, p):
    return {
        "business_id": str(business_id),
        "name": p["name"].strip(),
        "description": p.get("description", "").strip(),
        "category": p.get("category", "").strip(),
        "sku": p.get("sku", "").strip(),
        "price": float(p.get("price", 0)),
        "currency": p.get("currency", "KES"),
        "stock_quantity": float(p.get("stock_quantity", 0)),
        "unit": p.get("unit", "piece"),
        "image_url": p.get("image_url", "").strip(),
        "status": p.get("status", "active"),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }

def customer_document(business_id, p):
    return {
        "business_id": str(business_id),
        "name": p["name"].strip(),
        "phone": p.get("phone", "").strip(),
        "email": p.get("email", "").strip(),
        "notes": p.get("notes", "").strip(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }

def order_document(business_id, p):
    return {
        "business_id": str(business_id),
        "customer_id": str(p.get("customer_id")) if p.get("customer_id") else None,
        "items": p.get("items", []),
        "total_amount": float(p.get("total_amount", 0)),
        "currency": p.get("currency", "KES"),
        "status": "pending",
        "payment_status": "unpaid",
        "notes": p.get("notes", "").strip(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }

def expense_document(business_id, p):
    return {
        "business_id": str(business_id),
        "title": p["title"].strip(),
        "category": p.get("category", "").strip(),
        "amount": float(p["amount"]),
        "currency": p.get("currency", "KES"),
        "notes": p.get("notes", "").strip(),
        "created_at": now_utc(),
    }
