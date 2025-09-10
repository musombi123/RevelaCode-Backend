# backend/docs_routes.py
from flask import Blueprint, jsonify, current_app
from pymongo import MongoClient, errors
import os

docs_bp = Blueprint("docs", __name__)

# Read Mongo URI from environment only
MONGO_URI = os.environ.get("MONGO_URI")

client = None
db = None
legal_docs = None

if MONGO_URI:
    try:
        # Use TLS if URI is for Atlas, otherwise connect normally
        if "mongodb+srv://" in MONGO_URI:
            client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=False)
        else:
            client = MongoClient(MONGO_URI)

        db = client["revelacode"]
        legal_docs = db["legal_docs"]
    except errors.ConnectionFailure as e:
        current_app.logger.error(f"MongoDB connection failed: {e}")
        client = None
else:
    current_app.logger.warning("⚠️ MONGO_URI not set, docs endpoints will be unavailable.")


@docs_bp.route("/api/legal/<doc_type>", methods=["GET"])
def get_legal_doc(doc_type):
    if legal_docs is None:  # ✅ fixed check
        return jsonify({
            "status": "error",
            "message": "Database not connected. Check MONGO_URI."
        }), 500

    try:
        doc = legal_docs.find_one({"type": doc_type})
        if doc is None:  # ✅ also safer than `if not doc`
            return jsonify({
                "status": "error",
                "message": f"Document type '{doc_type}' not found"
            }), 404

        return jsonify({
            "status": "success",
            "type": doc["type"],
            "content": doc["content"],
            "version": doc.get("version", "1.0")
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }), 500
