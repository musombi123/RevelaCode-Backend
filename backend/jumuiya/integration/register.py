# backend/jumuiya/integration/register.py

from __future__ import annotations

from backend.jumuiya.core.database import ensure_indexes
from backend.jumuiya.core.errors import register_error_handlers

from backend.jumuiya.integration.auth_bridge import (
    install_auth_bridge,
)

from backend.jumuiya.identity.routes import identity_bp
from backend.jumuiya.wallet.routes import wallet_bp
from backend.jumuiya.marketplace.routes import marketplace_bp

from backend.jumuiya.biashara.routes import biashara_bp
from backend.jumuiya.shamba.routes import shamba_bp
from backend.jumuiya.elimu.routes import elimu_bp
from backend.jumuiya.community.routes import community_bp


# =========================================================
# JUMUIYA REGISTRATION
# =========================================================

def register_jumuiya(app):
    """
    Register the complete Jumuiya ecosystem inside
    the existing RevelaCode Flask application.

    Architecture:

        RevelaCode Authentication
                │
                ▼
        Jumuiya Authentication Bridge
                │
                ├── Identity
                ├── Wallet
                ├── Marketplace
                ├── Biashara
                ├── Shamba
                ├── Elimu
                └── Community
    """

    logger = app.logger

    logger.info(
        "=================================================="
    )
    logger.info(
        "Starting Jumuiya platform registration..."
    )

    # =====================================================
    # DATABASE / INDEXES
    # =====================================================

    try:

        ensure_indexes()

        logger.info(
            "✅ Jumuiya database indexes ready."
        )

    except Exception:

        logger.exception(
            "❌ Jumuiya database/index initialization failed."
        )

        raise

    # =====================================================
    # ERROR HANDLERS
    # =====================================================

    register_error_handlers(app)

    logger.info(
        "✅ Jumuiya error handlers registered."
    )

    # =====================================================
    # AUTHENTICATION BRIDGE
    # =====================================================

    install_auth_bridge(app)

    logger.info(
        "✅ Jumuiya authentication bridge installed."
    )

    # =====================================================
    # IDENTITY
    # =====================================================

    app.register_blueprint(
        identity_bp,
        url_prefix="/api/jumuiya/identity",
    )

    logger.info(
        "✅ Jumuiya Identity registered."
    )

    # =====================================================
    # WALLET
    # =====================================================

    app.register_blueprint(
        wallet_bp,
        url_prefix="/api/jumuiya/wallet",
    )

    logger.info(
        "✅ Jumuiya Wallet registered."
    )

    # =====================================================
    # MARKETPLACE
    # =====================================================

    app.register_blueprint(
        marketplace_bp,
        url_prefix="/api/jumuiya/marketplace",
    )

    logger.info(
        "✅ Jumuiya Marketplace registered."
    )

    # =====================================================
    # BIASHARA
    # =====================================================

    app.register_blueprint(
        biashara_bp,
        url_prefix="/api/jumuiya/biashara",
    )

    logger.info(
        "✅ Jumuiya Biashara registered."
    )

    # =====================================================
    # SHAMBA
    # =====================================================

    app.register_blueprint(
        shamba_bp,
        url_prefix="/api/jumuiya/shamba",
    )

    logger.info(
        "✅ Jumuiya Shamba registered."
    )

    # =====================================================
    # ELIMU
    # =====================================================

    app.register_blueprint(
        elimu_bp,
        url_prefix="/api/jumuiya/elimu",
    )

    logger.info(
        "✅ Jumuiya Elimu registered."
    )

    # =====================================================
    # COMMUNITY
    # =====================================================

    app.register_blueprint(
        community_bp,
        url_prefix="/api/jumuiya/community",
    )

    logger.info(
        "✅ Jumuiya Community registered."
    )

    # =====================================================
    # COMPLETE
    # =====================================================

    logger.info(
        "✅ Jumuiya platform registered successfully."
    )

    logger.info(
        "Hubs: Biashara | Shamba | Elimu | Community"
    )

    logger.info(
        "Shared: Identity | Wallet | Marketplace"
    )

    logger.info(
        "=================================================="
    )

    return True
