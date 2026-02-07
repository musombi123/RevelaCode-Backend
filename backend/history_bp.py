from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from datetime import datetime
from backend.db import db  # Mongo client

history_bp = Blueprint("history_bp", __name__)
users_col = db.get_collection("users")

# ---------------- HELPER ----------------
def sanitize_user_doc(doc: dict) -> dict:
    """Convert MongoDB ObjectId to string for JSON serialization."""
    if not doc:
        return doc
    doc_copy = doc.copy()
    if "_id" in doc_copy:
        doc_copy["_id"] = str(doc_copy["_id"])
    # Sanitize history entries if they contain ObjectIds
    history = doc_copy.get("history", [])
    sanitized_history = []
    for h in history:
        h_copy = h.copy()
        if "_id" in h_copy:
            h_copy["_id"] = str(h_copy["_id"])
        sanitized_history.append(h_copy)
    doc_copy["history"] = sanitized_history
    return doc_copy

# ---------------- ROUTE ----------------
@history_bp.route("/history", methods=["GET", "POST", "DELETE", "OPTIONS"])
@cross_origin(
    origins=[
        "https://revelacode-frontend.onrender.com",
        "https://www.revelacode-frontend.onrender.com"
    ],
    supports_credentials=True,
    methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-ADMIN-KEY", "X-Timestamp"]
)
def history():
    contact = request.headers.get("Authorization")
    if not contact:
        return jsonify({"success": False, "history": [], "message": "Unauthorized"}), 401

    user = users_col.find_one({"contact": contact})
    if not user:
        return jsonify({"success": False, "history": [], "message": "User not found"}), 404

    user = sanitize_user_doc(user)  # <-- sanitize ObjectIds

    # ---------- GET ----------
    if request.method == "GET":
        return jsonify({"success": True, "history": user.get("history", [])}), 200

    # ---------- POST ----------
    if request.method == "POST":
        entry = request.get_json(silent=True) or {}
        if not entry:
            return jsonify({
                "success": False,
                "history": user.get("history", []),
                "message": "No history entry provided"
            }), 400

        history_list = user.get("history", [])
        history_list.append({
            **entry,
            "timestamp": request.headers.get("X-Timestamp") or datetime.utcnow().isoformat()
        })

        users_col.update_one({"contact": contact}, {"$set": {"history": history_list}})
        return jsonify({"success": True, "history": history_list}), 201

    # ---------- DELETE ----------
    if request.method == "DELETE":
        users_col.update_one({"contact": contact}, {"$set": {"history": []}})
        return jsonify({"success": True, "history": []}), 200
