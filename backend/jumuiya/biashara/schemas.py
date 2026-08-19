from decimal import Decimal, InvalidOperation

def required_string(payload, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    return value.strip()

def money(payload, field, required=True):
    value = payload.get(field)
    if value is None and not required:
        return 0.0
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a valid number.")
    if number < 0:
        raise ValueError(f"{field} cannot be negative.")
    return number

def business_payload(payload):
    required_string(payload, "name")
    return payload

def product_payload(payload):
    required_string(payload, "name")
    money(payload, "price", False)
    money(payload, "stock_quantity", False)
    return payload

def customer_payload(payload):
    required_string(payload, "name")
    return payload

def order_payload(payload):
    if not isinstance(payload.get("items", []), list) or not payload.get("items"):
        raise ValueError("At least one order item is required.")
    money(payload, "total_amount", False)
    return payload

def expense_payload(payload):
    required_string(payload, "title")
    money(payload, "amount", True)
    return payload
