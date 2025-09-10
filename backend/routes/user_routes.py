from flask import Blueprint, request, jsonify
from backend.user_data import load_user_data, save_user_data

user_bp = Blueprint("user", __name__)

@user_bp.route("/api/user/<contact>", methods=["GET"])
def get_user(contact):
    data = load_user_data(contact)
    return jsonify({"status": "success", "data": data}), 200

@user_bp.route("/api/user/<contact>", methods=["PUT"])
def update_user(contact):
    body = request.json or {}
    history = body.get("history")
    settings = body.get("settings")

    save_user_data(contact, history=history, settings=settings)
    return jsonify({"status": "success", "message": "User data updated"}), 200
