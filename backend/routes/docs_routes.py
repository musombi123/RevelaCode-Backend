# backend/docs_routes.py
from flask import Blueprint, jsonify, current_app, request
from pymongo import MongoClient
from datetime import datetime
import os
import logging

docs_bp = Blueprint("docs", __name__)
logger = logging.getLogger(__name__)

# ---------- ENV ----------
MONGO_URI = os.environ.get("MONGO_URI")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
DB_NAME = os.environ.get("MONGO_DB_NAME", "revelacode")

# ---------- Mongo Objects ----------
client = None
db = None
legal_docs = None

def init_mongo():
    """Initialize MongoDB safely; do not crash on import."""
    global client, db, legal_docs

    if not MONGO_URI:
        logger.warning("MONGO_URI not set — legal docs API disabled")
        return

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        client.server_info()  # force connection test
        db = client[DB_NAME]
        legal_docs = db["legal_docs"]
        logger.info("Legal docs MongoDB connection established")
    except Exception as e:
        logger.error(f"Legal docs MongoDB connection failed: {e}")
        client = None
        db = None
        legal_docs = None

# Initialize Mongo ONCE
init_mongo()

# ---------- AUTH HELPER ----------
def require_admin(req):
    key = req.headers.get("X-ADMIN-KEY")
    return bool(key and ADMIN_API_KEY and key == ADMIN_API_KEY)

# ---------- PUBLIC ROUTES ----------
@docs_bp.route("/api/legal", methods=["GET"])
def list_legal_docs():
    """List all available legal document types."""
    if legal_docs is None:
        return jsonify({"status": "error", "message": "Legal docs database not available"}), 503
    try:
        docs = list(legal_docs.find({}, {"_id": 0, "type": 1}))
        types = [doc["type"] for doc in docs]
        return jsonify({"status": "success", "documents": types}), 200
    except Exception as e:
        current_app.logger.error(f"Error listing legal docs: {e}")
        return jsonify({"status": "error", "message": "Unexpected server error"}), 500

@docs_bp.route("/api/legal/<doc_type>", methods=["GET"])
def get_legal_doc(doc_type):
    """Fetch a specific legal document by type."""
    if legal_docs is None:
        return jsonify({"status": "error", "message": "Legal docs database not available"}), 503
    try:
        doc = legal_docs.find_one({"type": doc_type}, {"_id": 0})
        if doc is None:
            return jsonify({"status": "error", "message": f"Document type '{doc_type}' not found"}), 404
        return jsonify({
            "status": "success",
            "type": doc.get("type"),
            "content": doc.get("content"),
            "version": doc.get("version", "1.0")
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching legal doc '{doc_type}': {e}")
        return jsonify({"status": "error", "message": "Unexpected server error"}), 500

# ---------- ADMIN ROUTE ----------
@docs_bp.route("/api/admin/legal/<doc_type>", methods=["PUT"])
def update_legal_doc(doc_type):
    """Admin-only: Update or create a legal document."""
    if not require_admin(request):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if legal_docs is None:
        return jsonify({"status": "error", "message": "Database not available"}), 503

    data = request.get_json(silent=True)
    if not data or "content" not in data:
        return jsonify({"status": "error", "message": "Missing 'content'"}), 400

    content = data["content"]
    version = data.get("version", "1.0")

    try:
        result = legal_docs.update_one(
            {"type": doc_type},
            {"$set": {"content": content, "version": version,
                      "updated_at": datetime.utcnow(), "updated_by": "admin"}},
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
        return jsonify({"status": "error", "message": "Update failed"}), 500
