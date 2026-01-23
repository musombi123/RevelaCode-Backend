import os

# Load API keys from environment variables
ADMIN_KEY = os.getenv("ADMIN_API_KEY")
SUPPORT_KEY = os.getenv("SUPPORT_API_KEY")

def get_role(req):
    """
    Determine the role based on the X-API-KEY header.
    Returns "admin", "support", or None.
    """
    key = req.headers.get("X-API-KEY")
    if key == ADMIN_KEY:
        return "admin"
    if key == SUPPORT_KEY:
        return "support"
    return None
