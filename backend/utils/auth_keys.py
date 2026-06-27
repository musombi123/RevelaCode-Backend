import os

ADMIN_KEY = os.getenv("ADMIN_API_KEY")
SUPPORT_KEY = os.getenv("SUPPORT_API_KEY")

def get_role(req):
    key = req.headers.get("X-API-KEY")

    print("=" * 60)
    print("HEADER KEY :", repr(key))
    print("ADMIN KEY  :", repr(ADMIN_KEY))
    print("MATCH      :", key == ADMIN_KEY)
    print("=" * 60)

    if key == ADMIN_KEY:
        return "admin"

    if key == SUPPORT_KEY:
        return "support"

    return None