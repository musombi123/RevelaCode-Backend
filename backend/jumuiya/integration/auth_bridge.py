from flask import g

def get_current_user():
    # Connect this to the EXISTING RevelaCode authentication context.
    user = getattr(g, "revelacode_user", None)
    if user:
        return user
    user = getattr(g, "current_user", None)
    if user:
        return user
    return None

def install_auth_bridge(app):
    @app.before_request
    def _jumuiya_auth_bridge():
        user = get_current_user()
        if user:
            g.jumuiya_user = user
