"""
RevelaCode AI Gateway

Internal bridge between the RevelaCode platform layer and RevelaAI.

The AI Gateway exposes controlled, user-scoped platform context to
RevelaAI without giving the AI service direct access to MongoDB.
"""

from .routes import ai_gateway_bp


def register_ai_gateway(app):
    """
    Register the internal AI Gateway blueprint with the Flask application.
    """
    app.register_blueprint(
        ai_gateway_bp,
        url_prefix="/api/ai",
    )