def _text(data, key, required=False, max_len=300):
    value = data.get(key)
    if value is None: value = ""
    if not isinstance(value, str): raise ValueError(f"{key} must be text.")
    value = value.strip()
    if required and not value: raise ValueError(f"{key} is required.")
    if len(value) > max_len: raise ValueError(f"{key} is too long.")
    return value

def _number(data, key, required=False, minimum=0):
    value = data.get(key)
    if value is None and not required: return 0.0
    try: value = float(value)
    except (TypeError, ValueError): raise ValueError(f"{key} must be a number.")
    if value < minimum: raise ValueError(f"{key} must be at least {minimum}.")
    return value

def business_payload(data):
    if not isinstance(data, dict): raise ValueError("JSON object required.")
    return {k: _text(data, k, required=(k=="name")) for k in ["name","description","phone","email","location","county","category","logo_url"]}

def product_payload(data):
    if not isinstance(data, dict): raise ValueError("JSON object required.")
    return {
        "name": _text(data, "name", True, 160), "description": _text(data,"description",False,1000),
        "category": _text(data,"category",False,120), "sku": _text(data,"sku",False,80),
        "price": _number(data,"price",True), "currency": _text(data,"currency",False,8) or "KES",
        "stock_quantity": _number(data,"stock_quantity",False), "unit": _text(data,"unit",False,40) or "piece",
        "image_url": _text(data,"image_url",False,500), "status": _text(data,"status",False,30) or "active",
    }

def customer_payload(data):
    if not isinstance(data, dict): raise ValueError("JSON object required.")
    return {k: _text(data,k,required=(k=="name")) for k in ["name","phone","email","notes"]}

def order_payload(data):
    if not isinstance(data, dict): raise ValueError("JSON object required.")
    items = data.get("items", [])
    if not isinstance(items, list): raise ValueError("items must be a list.")
    return {
        "customer_id": str(data.get("customer_id")) if data.get("customer_id") else None,
        "items": items, "total_amount": _number(data,"total_amount",True),
        "currency": _text(data,"currency",False,8) or "KES", "notes": _text(data,"notes",False,1000),
    }

def expense_payload(data):
    if not isinstance(data, dict): raise ValueError("JSON object required.")
    return {"title": _text(data,"title",True), "category": _text(data,"category",False), "amount": _number(data,"amount",True), "currency": _text(data,"currency",False,8) or "KES", "notes": _text(data,"notes",False,1000)}
