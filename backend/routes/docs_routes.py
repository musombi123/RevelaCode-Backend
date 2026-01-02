# backend/docs_routes.py
from flask import Blueprint, jsonify, current_app
from pymongo import MongoClient, errors
import os
import logging

docs_bp = Blueprint("docs", __name__)
logger = logging.getLogger(__name__)

# ---------- Mongo Config ----------
MONGO_URI = os.environ.get("MONGO_URI")

client = None
db = None
legal_docs = None

def init_mongo():
    global client, db, legal_docs

    if not MONGO_URI:
        logger.warning("MONGO_URI not set — legal docs API disabled")
        return

    try:
        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=3000
        )
        client.server_info()

        db_name = os.environ.get("MONGO_DB_NAME", "revelacode")
        db = client[db_name]
        legal_docs = db["legal_docs"]

        logger.info("Legal docs MongoDB connection established")

    except Exception as e:
        logger.error(f"Legal docs MongoDB connection failed: {e}")
        client = None
        db = None
        legal_docs = None

# ---------- Routes ----------
@docs_bp.route("/api/legal/<doc_type>", methods=["GET"])
def get_legal_doc(doc_type):
    if legal_docs is None:
        return jsonify({
            "status": "error",
            "message": "Legal docs database not available"
        }), 503

    try:
        doc = legal_docs.find_one(
            {"type": doc_type},
            {"_id": 0}
        )

        if doc is None:
            return jsonify({
                "status": "error",
                "message": f"Document type '{doc_type}' not found"
            }), 404

        return jsonify({
            "status": "success",
            "type": doc.get("type"),
            "content": doc.get("content"),
            "version": doc.get("version", "1.0")
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error fetching legal doc: {e}")
        return jsonify({
            "status": "error",
            "message": "Unexpected server error"
        }), 500
