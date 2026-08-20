from datetime import datetime,timezone

def listing_document(user_id,data):
    return {"seller_user_id":str(user_id),"title":data["title"],"description":data.get("description",""),"category":data.get("category","general"),"hub":data.get("hub","community"),"price":float(data.get("price",0)),"currency":data.get("currency","KES"),"unit":data.get("unit","piece"),"quantity_available":float(data.get("quantity_available",1)),"location":data.get("location",""),"status":"active","created_at":datetime.now(timezone.utc),"updated_at":datetime.now(timezone.utc)}
