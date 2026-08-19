# Add/adapt inside the EXISTING RevelaCode Flask app factory or main.py:

from jumuiya.integration.register import register_jumuiya

register_jumuiya(app)

# IMPORTANT:
# Your existing auth middleware must expose the authenticated user as:
# g.revelacode_user
#
# If it uses another mechanism, edit jumuiya/integration/auth_bridge.py.
