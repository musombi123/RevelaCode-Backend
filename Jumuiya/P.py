from pathlib import Path
import zipfile, textwrap, shutil

root = Path("/mnt/data/RevelaCode-Jumuiya-Backend-Biashara-v1")
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)

files = {
"README.md": """# RevelaCode Jumuiya Backend — Biashara v1

This is a modular extension to the existing RevelaCode Flask + MongoDB backend.
It does NOT replace the existing Bible, Prophecy, Events, Referential, RevelaAI,
or authentication systems.

## Phase 1
- Shared Jumuiya integration
- Existing-auth bridge
- Biashara business profile
- Products
- Customers
- Orders
- Expenses
- Dashboard metrics
- MongoDB indexes
- API contract
- Basic schema tests

## Register inside existing main.py / app factory

from jumuiya.integration.register import register_jumuiya
register_jumuiya(app)

The auth bridge expects the existing RevelaCode auth middleware to expose the
authenticated user as `g.revelacode_user`. Change only
`jumuiya/integration/auth_bridge.py` if your existing auth uses another context.

API base:
`/api/jumuiya/biashara`

Next modules should be added beside `biashara/`:
`shamba/`, `elimu/`, and `community/`.

Architecture:
ONE RevelaCode frontend + ONE RevelaCode backend + ONE identity + multiple hubs.
""",

"jumuiya/__init__.py": "",
"jumuiya/core/__init__.py": "",
"jumuiya/biashara/__init__.py": "",
"jumuiya/integration/__init__.py": "",

"jumuiya/config.py": """
import os

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME") or os.getenv("MONGODB_DB") or "revelacode"
""",

"jumuiya/core/database.py": """
from pymongo import MongoClient, ASCENDING, DESCENDING
from jumuiya.config import MONGO_URI, MONGO_DB_NAME

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is not None:
        return _db
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI/MONGODB_URI is not configured.")
    _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    _db = _client[MONGO_DB_NAME]
    _client.admin.command("ping")
    return _db

def collection(name):
    return get_db()[name]

def ensure_indexes():
    db = get_db()
    db["jumuiya_businesses"].create_index([("owner_user_id", ASCENDING)], unique=True)
    db["jumuiya_businesses"].create_index([("slug", ASCENDING)], unique=True)
    db["jumuiya_products"].create_index([("business_id", ASCENDING), ("status", ASCENDING)])
    db["jumuiya_customers"].create_index([("business_id", ASCENDING), ("created_at", DESCENDING)])
    db["jumuiya_orders"].create_index([("business_id", ASCENDING), ("created_at", DESCENDING)])
    db["jumuiya_sales"].create_index([("business_id", ASCENDING), ("sold_at", DESCENDING)])
    db["jumuiya_expenses"].create_index([("business_id", ASCENDING), ("spent_at", DESCENDING)])
    db["jumuiya_inventory_movements"].create_index(
        [("business_id", ASCENDING), ("product_id", ASCENDING), ("created_at", DESCENDING)]
    )
""",

"jumuiya/core/errors.py": """
from flask import jsonify

class APIError(Exception):
    def __init__(self, message, status_code=400, code="bad_request"):
        self.message = message
        self.status_code = status_code
        self.code = code

def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify({
            "success": False,
            "error": {"code": error.code, "message": error.message}
        }), error.status_code
""",

"jumuiya/core/responses.py": """
from flask import jsonify

def ok(data=None, message=None, status_code=200):
    payload = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code

def created(data=None, message="Created successfully"):
    return ok(data, message, 201)
""",

"jumuiya/core/permissions.py": """
from functools import wraps
from flask import g
from jumuiya.core.errors import APIError

def require_authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not getattr(g, "jumuiya_user", None):
            raise APIError("Authentication is required.", 401, "authentication_required")
        return fn(*args, **kwargs)
    return wrapper

def current_user_id():
    user = getattr(g, "jumuiya_user", None)
    if not user:
        raise APIError("Authentication is required.", 401, "authentication_required")
    value = user.get("id") or user.get("_id") or user.get("user_id")
    if value is None:
        raise APIError("Authenticated user has no usable ID.", 401, "invalid_identity")
    return str(value)
""",

"jumuiya/integration/auth_bridge.py": """
from flask import g

def get_current_user():
    # Connect this to the EXISTING RevelaCode authentication context.
    user = getattr(g, "revelacode_user", None)
    if user:
        return user
    user = getattr(g, "current_user", None)
    if user:
        return user
    return None

def install_auth_bridge(app):
    @app.before_request
    def _jumuiya_auth_bridge():
        user = get_current_user()
        if user:
            g.jumuiya_user = user
""",

"jumuiya/integration/register.py": """
from jumuiya.integration.auth_bridge import install_auth_bridge
from jumuiya.core.database import ensure_indexes
from jumuiya.core.errors import register_error_handlers
from jumuiya.biashara.routes import biashara_bp

def register_jumuiya(app):
    app.register_blueprint(biashara_bp, url_prefix="/api/jumuiya/biashara")
    install_auth_bridge(app)
    register_error_handlers(app)
    ensure_indexes()
    return app
""",

"jumuiya/biashara/models.py": """
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
""",

"jumuiya/biashara/schemas.py": """
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
""",

"jumuiya/biashara/services.py": """
import re
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from jumuiya.core.database import collection
from jumuiya.core.errors import APIError
from jumuiya.biashara.models import business_document, product_document, customer_document, order_document, expense_document

def clean_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value

def serialise(doc):
    if not doc:
        return None
    result = dict(doc)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    for k, v in list(result.items()):
        if isinstance(v, ObjectId):
            result[k] = str(v)
    return result

def serialise_many(docs):
    return [serialise(d) for d in docs]

def slugify(value):
    value = re.sub(r"[^a-zA-Z0-9\\s-]", "", value.lower())
    return re.sub(r"[\\s_-]+", "-", value).strip("-") or "business"

def unique_slug(name):
    base = slugify(name)
    slug = base
    n = 2
    while collection("jumuiya_businesses").find_one({"slug": slug}):
        slug = f"{base}-{n}"
        n += 1
    return slug

def get_business_for_user(user_id):
    return serialise(collection("jumuiya_businesses").find_one({"owner_user_id": str(user_id)}))

def create_or_update_business(user_id, p):
    c = collection("jumuiya_businesses")
    old = c.find_one({"owner_user_id": str(user_id)})
    if old:
        update = {k: p.get(k, "") for k in [
            "name", "description", "phone", "email", "location", "county", "category", "logo_url"
        ]}
        update["updated_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        return serialise(c.find_one_and_update(
            {"_id": old["_id"]}, {"$set": update}, return_document=ReturnDocument.AFTER
        ))
    doc = business_document(user_id, p, unique_slug(p["name"]))
    r = c.insert_one(doc); doc["_id"] = r.inserted_id
    return serialise(doc)

def create_product(user_id, p):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Create your business profile first.", 409, "business_required")
    doc = product_document(b["id"], p)
    r = collection("jumuiya_products").insert_one(doc); doc["_id"] = r.inserted_id
    return serialise(doc)

def list_products(user_id, status=None):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    q = {"business_id": b["id"]}
    if status: q["status"] = status
    return serialise_many(collection("jumuiya_products").find(q).sort("created_at", -1))

def update_product(user_id, product_id, p):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    allowed = ["name","description","category","sku","price","currency","stock_quantity","unit","image_url","status"]
    update = {k: p[k] for k in allowed if k in p}
    if "price" in update: update["price"] = float(update["price"])
    if "stock_quantity" in update: update["stock_quantity"] = float(update["stock_quantity"])
    if not update: raise APIError("No fields supplied for update.", 400, "empty_update")
    doc = collection("jumuiya_products").find_one_and_update(
        {"_id": clean_id(product_id), "business_id": b["id"]},
        {"$set": update}, return_document=ReturnDocument.AFTER
    )
    if not doc: raise APIError("Product not found.", 404, "product_not_found")
    return serialise(doc)

def create_customer(user_id, p):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    doc = customer_document(b["id"], p)
    r = collection("jumuiya_customers").insert_one(doc); doc["_id"] = r.inserted_id
    return serialise(doc)

def list_customers(user_id):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    return serialise_many(collection("jumuiya_customers").find({"business_id": b["id"]}).sort("created_at", -1))

def create_order(user_id, p):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    doc = order_document(b["id"], p)
    r = collection("jumuiya_orders").insert_one(doc); doc["_id"] = r.inserted_id
    return serialise(doc)

def list_orders(user_id, status=None):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    q = {"business_id": b["id"]}
    if status: q["status"] = status
    return serialise_many(collection("jumuiya_orders").find(q).sort("created_at", -1))

def create_expense(user_id, p):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    doc = expense_document(b["id"], p)
    r = collection("jumuiya_expenses").insert_one(doc); doc["_id"] = r.inserted_id
    return serialise(doc)

def dashboard(user_id):
    b = get_business_for_user(user_id)
    if not b: raise APIError("Business profile not found.", 404, "business_not_found")
    bid = b["id"]
    products = collection("jumuiya_products")
    orders = collection("jumuiya_orders")
    sales = collection("jumuiya_sales")
    expenses = collection("jumuiya_expenses")
    customers = collection("jumuiya_customers")

    sales_agg = list(sales.aggregate([{"$match":{"business_id":bid}}, {"$group":{"_id":None,"total":{"$sum":"$amount"}}}]))
    expense_agg = list(expenses.aggregate([{"$match":{"business_id":bid}}, {"$group":{"_id":None,"total":{"$sum":"$amount"}}}]))
    total_sales = float(sales_agg[0]["total"]) if sales_agg else 0.0
    total_expenses = float(expense_agg[0]["total"]) if expense_agg else 0.0

    return {
        "business": b,
        "metrics": {
            "products": products.count_documents({"business_id":bid, "status":{"$ne":"deleted"}}),
            "low_stock": products.count_documents({"business_id":bid, "status":"active", "stock_quantity":{"$lte":5}}),
            "customers": customers.count_documents({"business_id":bid}),
            "pending_orders": orders.count_documents({"business_id":bid, "status":{"$in":["pending","confirmed","processing"]}}),
            "sales_total": total_sales,
            "expenses_total": total_expenses,
            "net_estimate": total_sales-total_expenses
        }
    }
""",

"jumuiya/biashara/routes.py": """
from flask import Blueprint, request
from jumuiya.core.permissions import require_authenticated, current_user_id
from jumuiya.core.responses import ok, created
from jumuiya.core.errors import APIError
from jumuiya.biashara import schemas, services

biashara_bp = Blueprint("jumuiya_biashara", __name__)

def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data

def validate(fn, data):
    try:
        return fn(data)
    except ValueError as e:
        raise APIError(str(e), 422, "validation_error")

@biashara_bp.get("/health")
def health():
    return ok({"hub":"biashara","status":"online"})

@biashara_bp.get("/business")
@require_authenticated
def get_business():
    return ok(services.get_business_for_user(current_user_id()))

@biashara_bp.post("/business")
@require_authenticated
def save_business():
    return ok(services.create_or_update_business(current_user_id(), validate(schemas.business_payload, body())), "Business profile saved.")

@biashara_bp.get("/products")
@require_authenticated
def get_products():
    return ok(services.list_products(current_user_id(), request.args.get("status")))

@biashara_bp.post("/products")
@require_authenticated
def add_product():
    return created(services.create_product(current_user_id(), validate(schemas.product_payload, body())), "Product created.")

@biashara_bp.put("/products/<product_id>")
@require_authenticated
def edit_product(product_id):
    return ok(services.update_product(current_user_id(), product_id, validate(schemas.product_payload, body())), "Product updated.")

@biashara_bp.get("/customers")
@require_authenticated
def get_customers():
    return ok(services.list_customers(current_user_id()))

@biashara_bp.post("/customers")
@require_authenticated
def add_customer():
    return created(services.create_customer(current_user_id(), validate(schemas.customer_payload, body())), "Customer created.")

@biashara_bp.get("/orders")
@require_authenticated
def get_orders():
    return ok(services.list_orders(current_user_id(), request.args.get("status")))

@biashara_bp.post("/orders")
@require_authenticated
def add_order():
    return created(services.create_order(current_user_id(), validate(schemas.order_payload, body())), "Order created.")

@biashara_bp.post("/expenses")
@require_authenticated
def add_expense():
    return created(services.create_expense(current_user_id(), validate(schemas.expense_payload, body())), "Expense recorded.")

@biashara_bp.get("/dashboard")
@require_authenticated
def get_dashboard():
    return ok(services.dashboard(current_user_id()))
""",

"requirements-jumuiya.txt": """# Install only what the existing backend does not already have.
Flask>=3.0,<4
pymongo>=4.6,<5
pytest>=8,<9
""",

".env.example": """# Reuse the SAME MongoDB environment as RevelaCode
MONGO_URI=mongodb+srv://USERNAME:PASSWORD@CLUSTER/DATABASE
MONGO_DB_NAME=revelacode
""",

"INTEGRATION_SNIPPET.py": """# Add/adapt inside the EXISTING RevelaCode Flask app factory or main.py:

from jumuiya.integration.register import register_jumuiya

register_jumuiya(app)

# IMPORTANT:
# Your existing auth middleware must expose the authenticated user as:
# g.revelacode_user
#
# If it uses another mechanism, edit jumuiya/integration/auth_bridge.py.
""",

"API_CONTRACT.md": """# Biashara API

Base: /api/jumuiya/biashara

GET  /health
GET  /business
POST /business

GET  /products
POST /products
PUT  /products/{id}

GET  /customers
POST /customers

GET  /orders
POST /orders

POST /expenses

GET  /dashboard

Business body:
{
  "name":"Mama Njeri Shop",
  "description":"General retail shop",
  "phone":"07XXXXXXXX",
  "location":"Kongowea",
  "county":"Mombasa",
  "category":"Retail"
}

Product body:
{
  "name":"Exercise Book",
  "category":"Stationery",
  "sku":"EX-096",
  "price":80,
  "stock_quantity":50,
  "unit":"piece",
  "currency":"KES"
}

Order body:
{
  "customer_id":"optional-id",
  "items":[
    {"product_id":"product-id","name":"Exercise Book","quantity":2,"unit_price":80}
  ],
  "total_amount":160,
  "currency":"KES"
}

Expense body:
{
  "title":"Transport",
  "category":"Operations",
  "amount":300,
  "currency":"KES"
}

NOTE:
Dashboard sales/expense totals are operational metrics, NOT yet a legally
auditable accounting ledger. Live payments require an immutable transaction
ledger and M-Pesa reconciliation layer.
""",

"tests/test_schemas.py": """import pytest
from jumuiya.biashara.schemas import business_payload, product_payload, customer_payload, order_payload, expense_payload

def test_business_requires_name():
    with pytest.raises(ValueError): business_payload({})

def test_product_requires_name():
    with pytest.raises(ValueError): product_payload({"price":10})

def test_customer_requires_name():
    with pytest.raises(ValueError): customer_payload({})

def test_order_requires_items():
    with pytest.raises(ValueError): order_payload({"items":[]})

def test_expense_requires_title():
    with pytest.raises(ValueError): expense_payload({"amount":100})
"""
}

for rel, content in files.items():
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

zip_path = Path("/mnt/data/RevelaCode-Jumuiya-Backend-Biashara-v1.zip")
if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob("*"):
        if p.is_file():
            z.write(p, p.relative_to(root.parent))

print(f"READY: {zip_path}")
print(f"Files created: {sum(1 for p in root.rglob('*') if p.is_file())}")
