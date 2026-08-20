from datetime import datetime,timezone

def notification_document(user_id,data):
    return {"user_id":str(user_id),"title":data["title"],"message":data["message"],"type":data.get("type","info"),"read":False,"data":data.get("data",{}),"created_at":datetime.now(timezone.utc)}
