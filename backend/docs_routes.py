# backend/docs_routes.py
from flask import Blueprint, jsonify
import os, json

docs_bp = Blueprint("docs", __name__)

@docs_bp.route("/api/docs/<string:doc_type>", methods=["GET"])
def get_doc(doc_type):
    file_map = {
        "privacy": "privacy_policy.json",
        "terms": "terms_of_service.json"
    }
    filename = file_map.get(doc_type)
    if not filename:
        return jsonify({"status": "error", "message": "Invalid document type"}), 400

    path = os.path.join("backend", "docs", filename)
    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "Document not found"}), 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data), 200
