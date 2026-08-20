from datetime import datetime, timezone

def post_document(user_id, data):
    now=datetime.now(timezone.utc)
    return {
        "author_user_id":str(user_id),
        "title":data["title"],
        "body":data["body"],
        "category":data.get("category","general"),
        "hub":data.get("hub","community"),
        "location":data.get("location",""),
        "status":"published",
        "likes_count":0,
        "comments_count":0,
        "created_at":now,
        "updated_at":now,
    }
