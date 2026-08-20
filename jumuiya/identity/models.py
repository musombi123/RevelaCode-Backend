from datetime import datetime,timezone

def profile_document(user):
    now=datetime.now(timezone.utc)
    return {"user_id":str(user["id"]),"full_name":user.get("full_name",""),"contact":user.get("contact",""),"roles":user.get("roles",["user"]),"bio":"","avatar_url":"","county":"","town":"","created_at":now,"updated_at":now}
