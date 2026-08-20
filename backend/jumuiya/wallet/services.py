from jumuiya.core.database import collection
from jumuiya.core.errors import APIError
from jumuiya.core.audit import log_action
from jumuiya.wallet.models import transaction_document

def ledger(user_id):
    docs=list(collection("jumuiya_transactions").find({"user_id":str(user_id)}).sort("created_at",-1))
    balance=0.0
    out=[]
    for d in docs:
        amount=float(d.get("amount",0)); balance += amount if d.get("direction")=="credit" else -amount
        out.append(_ser(d))
    return {"balance":balance,"currency":"KES","transactions":out}

def record_transaction(user_id,data):
    try: amount=float(data.get("amount"))
    except (TypeError,ValueError):raise APIError("amount must be a number.",422,"validation_error")
    if amount<=0:raise APIError("amount must be greater than zero.",422,"validation_error")
    if data.get("direction") not in {"credit","debit"}:raise APIError("direction must be credit or debit.",422,"validation_error")
    doc=transaction_document(user_id,{**data,"amount":amount}); r=collection("jumuiya_transactions").insert_one(doc); doc["_id"]=r.inserted_id; log_action(user_id,"wallet.transaction.recorded","transaction",r.inserted_id); return _ser(doc)

def _ser(doc):
    out=dict(doc);
    if "_id" in out:out["id"]=str(out.pop("_id"))
    for k,v in list(out.items()):
        if hasattr(v,"isoformat"):out[k]=v.isoformat()
    return out
