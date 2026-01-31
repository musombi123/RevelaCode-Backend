from flask import Blueprint, request, jsonify
from .user_helpers import save_user_data, load_user_data

user_bp = Blueprint("user", __name__)

# ------------------- ROUTES -------------------

@user_bp.route("/api/user/<contact>", methods=["GET"])
def get_user(contact):
    user_data = load_user_data(contact)

    # FIX: you were checking an undefined variable `users`
    if user_data is None:
        save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})
        user_data = load_user_data(contact)

    return jsonify(user_data), 200


@user_bp.route("/api/user/<contact>", methods=["POST"])
def update_user(contact):
    data = request.get_json(silent=True) or {}
    history = data.get("history")
    settings = data.get("settings")

    existing = load_user_data(contact)
    if existing is None:
        save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})

    if history is not None or settings is not None:
        save_user_data(contact, history=history, settings=settings)

    return jsonify({"status": "success", "message": f"User data updated for {contact}"}), 200
