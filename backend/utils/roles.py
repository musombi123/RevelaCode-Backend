import os

ADMIN_KEY = os.getenv("ADMIN_API_KEY")
SUPPORT_KEY = os.getenv("SUPPORT_API_KEY")

def get_role(req):
    key = req.headers.get("X-API-KEY")
    if key == ADMIN_KEY:
        return "admin"
    if key == SUPPORT_KEY:
        return "support"
    return None
