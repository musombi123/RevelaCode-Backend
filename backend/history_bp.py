# backend/user_data/history_bp.py
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from backend.auth_gate import get_user_from_file, MONGO_AVAILABLE, users_col

history_bp = Blueprint("history_bp", __name__)

@history_bp.route("/history", methods=["GET", "OPTIONS"])
@cross_origin(
    origins=[
        "https://revelacode-frontend.onrender.com",
        "https://www.revelacode-frontend.onrender.com"
    ],
    supports_credentials=True,
    methods=["GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-ADMIN-KEY"]
)
def get_history():
    # Example: using Authorization header as the contact for simplicity
    contact = request.headers.get("Authorization")
    if not contact:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    user = users_col.find_one({"contact": contact}) if MONGO_AVAILABLE else get_user_from_file(contact)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    return jsonify({"success": True, "history": user.get("history", [])}), 200
