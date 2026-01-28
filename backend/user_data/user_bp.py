from flask import Blueprint, request, jsonify
from .user_helpers import save_user_data, load_user_data

user_bp = Blueprint("user", __name__)

# ------------------- ROUTES -------------------

@user_bp.route("/api/user/<contact>", methods=["GET"])
def get_user(contact):
    """
    Fetch user data (history + settings).
    If user data doesn't exist yet, auto-initialize defaults.
    """
    user_data = load_user_data(contact)
    # Auto-initialize if missing
    if user_data is None:
        save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})
        user_data = load_user_data(contact)
    return jsonify(user_data), 200


@user_bp.route("/api/user/<contact>", methods=["POST"])
def update_user(contact):
    """
    Update user history or settings.
    Partial updates allowed — only pass what you want to update.
    """
    data = request.get_json(silent=True) or {}
    history = data.get("history")
    settings = data.get("settings")

    # Auto-load existing user_data if missing
    existing = load_user_data(contact)
    if existing is None:
        save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})

    save_user_data(contact, history=history, settings=settings)
    return jsonify({"status": "success", "message": f"User data updated for {contact}"}), 200
