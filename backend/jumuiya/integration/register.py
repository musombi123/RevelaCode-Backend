from jumuiya.integration.auth_bridge import install_auth_bridge
from jumuiya.core.database import ensure_indexes
from jumuiya.core.errors import register_error_handlers
from jumuiya.biashara.routes import biashara_bp

def register_jumuiya(app):
    app.register_blueprint(biashara_bp, url_prefix="/api/jumuiya/biashara")
    install_auth_bridge(app)
    register_error_handlers(app)
    ensure_indexes()
    return app
