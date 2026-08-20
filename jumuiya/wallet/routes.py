from flask import Blueprint,request
from jumuiya.core.permissions import require_authenticated,current_user_id
from jumuiya.core.responses import ok,created
from jumuiya.wallet import services

wallet_bp=Blueprint("jumuiya_wallet",__name__)

@wallet_bp.get("/ledger")
@require_authenticated
def get_ledger():return ok(services.ledger(current_user_id()))

@wallet_bp.post("/transactions")
@require_authenticated
def add_transaction():return created(services.record_transaction(current_user_id(),request.get_json(silent=True) or {}),"Transaction recorded.")
