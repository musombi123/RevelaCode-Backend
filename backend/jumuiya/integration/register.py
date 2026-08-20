from jumuiya.core.database import ensure_indexes
from jumuiya.core.errors import register_error_handlers
from jumuiya.integration.auth_bridge import install_auth_bridge
from jumuiya.biashara.routes import biashara_bp
from jumuiya.community.routes import community_bp
from jumuiya.marketplace.routes import marketplace_bp
from jumuiya.health_routes import jumuiya_health_bp
from jumuiya.identity.routes import identity_bp
from jumuiya.wallet.routes import wallet_bp
from jumuiya.notifications.routes import notifications_bp

def register_jumuiya(app):
    app.register_blueprint(jumuiya_health_bp, url_prefix="/api/jumuiya")
    app.register_blueprint(identity_bp, url_prefix="/api/jumuiya/identity")
    app.register_blueprint(wallet_bp, url_prefix="/api/jumuiya/wallet")
    app.register_blueprint(notifications_bp, url_prefix="/api/jumuiya/notifications")
    app.register_blueprint(biashara_bp, url_prefix="/api/jumuiya/biashara")
    app.register_blueprint(community_bp, url_prefix="/api/jumuiya/community")
    app.register_blueprint(marketplace_bp, url_prefix="/api/jumuiya/marketplace")
    install_auth_bridge(app)
    register_error_handlers(app)
    try:
        ensure_indexes()
    except Exception as exc:
        app.logger.warning("Jumuiya indexes unavailable at startup: %s", exc)
    return app
