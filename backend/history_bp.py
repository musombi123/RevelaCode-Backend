from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from backend.db import db  # Mongo client

history_bp = Blueprint("history_bp", __name__)
users_col = db.get_collection("users")

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

    # GET
    if request.method == "GET":
        return jsonify({"success": True, "history": user.get("history", [])}), 200

    # POST
    if request.method == "POST":
        entry = request.get_json(silent=True) or {}
        if not entry:
            return jsonify({"success": False, "history": user.get("history", []), "message": "No history entry provided"}), 400

        history_list = user.get("history", [])
        history_list.append({
            **entry,
            "timestamp": request.headers.get("X-Timestamp") or datetime.utcnow().isoformat()
        })
        users_col.update_one({"contact": contact}, {"$set": {"history": history_list}})

        return jsonify({"success": True, "history": history_list}), 201

    # DELETE
    if request.method == "DELETE":
        users_col.update_one({"contact": contact}, {"$set": {"history": []}})
        return jsonify({"success": True, "history": []}), 200
