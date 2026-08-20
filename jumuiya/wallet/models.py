from datetime import datetime,timezone

def transaction_document(user_id,data):
    return {"user_id":str(user_id),"type":data["type"],"direction":data["direction"],"amount":float(data["amount"]),"currency":data.get("currency","KES"),"reference":data.get("reference",""),"description":data.get("description",""),"status":data.get("status","completed"),"created_at":datetime.now(timezone.utc)}
