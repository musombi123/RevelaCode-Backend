# backend/docs_routes.py
from flask import Blueprint, jsonify
from pymongo import MongoClient
import os

docs_bp = Blueprint("docs", __name__)

# Connect to MongoDB
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/revelacode")
client = MongoClient(MONGO_URI)
db = client.get_database()
legal_docs = db.legal_docs  # same collection you seeded

@docs_bp.route("/api/legal/<doc_type>", methods=["GET"])
def get_legal_doc(doc_type):
    try:
        doc = legal_docs.find_one({"type": doc_type})
        if not doc:
            return jsonify({"status": "error", "message": f"{doc_type} not found"}), 404
        return jsonify({
            "status": "success",
            "type": doc["type"],
            "content": doc["content"],
            "version": doc.get("version", "1.0")
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
