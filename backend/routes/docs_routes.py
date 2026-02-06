# backend/routes/docs_routes.py
from flask import Blueprint, jsonify, current_app, request
from datetime import datetime
import os
import logging

from backend.db import get_db  # ✅ use shared DB

docs_bp = Blueprint("docs", __name__)
logger = logging.getLogger(__name__)

# ---------- ENV ----------
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# ---------- Mongo Objects ----------
db = None
legal_docs = None


def init_mongo():
    """
    Initialize MongoDB safely using shared connection.
    Compatible with Mongoose defaults.
    """
    global db, legal_docs

    try:
        db = get_db()

        # ✅ Mongoose pluralized collection name
        legal_docs = db["legaldocs"]

        logger.info("✅ Legal docs MongoDB ready")

    except Exception as e:
        logger.error(f"❌ Legal docs Mongo init failed: {e}")
        db = None
        legal_docs = None


# Initialize once
init_mongo()


# ---------- AUTH HELPER ----------
def require_admin(req):
    key = req.headers.get("X-ADMIN-KEY")
    return bool(key and ADMIN_API_KEY and key == ADMIN_API_KEY)


# ---------- PUBLIC ROUTE ----------
@docs_bp.route("/api/legal/<doc_type>", methods=["GET"])
def get_legal_doc(doc_type):
    if legal_docs is None:
        return jsonify({
            "status": "error",
            "message": "Legal docs database not available"
        }), 503

    try:
        doc = legal_docs.find_one({"type": doc_type}, {"_id": 0})

        if not doc:
            return jsonify({
                "status": "error",
                "message": f"Document type '{doc_type}' not found"
            }), 404

        return jsonify({
            "status": "success",
            "type": doc["type"],
            "content": doc["content"],
            "version": doc.get("version", "1.0"),
            "note": "👋 You are viewing as a guest. Login to save history."
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching legal doc: {e}")
        return jsonify({
            "status": "error",
            "message": "Unexpected server error"
        }), 500


# ---------- ADMIN ROUTE ----------
@docs_bp.route("/api/admin/legal/<doc_type>", methods=["PUT"])
def update_legal_doc(doc_type):
    if not require_admin(request):
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 401

    if legal_docs is None:
        return jsonify({
            "status": "error",
            "message": "Database not available"
        }), 503

    data = request.get_json(silent=True)
    if not data or "content" not in data:
        return jsonify({
            "status": "error",
            "message": "Missing 'content'"
        }), 400

    try:
        result = legal_docs.update_one(
            {"type": doc_type},
            {
                "$set": {
                    "content": data["content"],
                    "version": data.get("version", "1.0"),
                    "updated_at": datetime.utcnow(),
                    "updated_by": "admin"
                }
            },
            upsert=True
        )

        return jsonify({
            "status": "success",
            "type": doc_type,
            "updated": True,
            "upserted": result.upserted_id is not None
        }), 200

    except Exception as e:
        logger.error(f"Admin legal doc update failed: {e}")
        return jsonify({
            "status": "error",
            "message": "Update failed"
        }), 500
