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
    try: return fn(data)
    except ValueError as exc: raise APIError(str(exc), 422, "validation_error")

@biashara_bp.get("/health")
def health(): return ok({"hub":"biashara","status":"online"})

@biashara_bp.get("/business")
@require_authenticated
def get_business(): return ok(services.get_business_for_user(current_user_id()))

@biashara_bp.post("/business")
@require_authenticated
def save_business(): return ok(services.create_or_update_business(current_user_id(), validate(schemas.business_payload, body())), "Business profile saved.")

@biashara_bp.get("/products")
@require_authenticated
def get_products(): return ok(services.list_products(current_user_id(), request.args.get("status")))

@biashara_bp.post("/products")
@require_authenticated
def add_product(): return created(services.create_product(current_user_id(), validate(schemas.product_payload, body())), "Product created.")

@biashara_bp.put("/products/<product_id>")
@require_authenticated
def edit_product(product_id): return ok(services.update_product(current_user_id(), product_id, validate(schemas.product_payload, body())), "Product updated.")

@biashara_bp.get("/customers")
@require_authenticated
def get_customers(): return ok(services.list_customers(current_user_id()))

@biashara_bp.post("/customers")
@require_authenticated
def add_customer(): return created(services.create_customer(current_user_id(), validate(schemas.customer_payload, body())), "Customer created.")

@biashara_bp.get("/orders")
@require_authenticated
def get_orders(): return ok(services.list_orders(current_user_id(), request.args.get("status")))

@biashara_bp.post("/orders")
@require_authenticated
def add_order(): return created(services.create_order(current_user_id(), validate(schemas.order_payload, body())), "Order created.")

@biashara_bp.post("/expenses")
@require_authenticated
def add_expense(): return created(services.create_expense(current_user_id(), validate(schemas.expense_payload, body())), "Expense recorded.")

@biashara_bp.get("/dashboard")
@require_authenticated
def get_dashboard(): return ok(services.dashboard(current_user_id()))
