# backend/delete_account_api.py
import os, json, random
from flask import Blueprint, request, jsonify
from verify import load_users, save_users

delete_bp = Blueprint("delete", __name__)

@delete_bp.route("/api/delete-account", methods=["POST"])
def delete_account_api():
    data = request.get_json(force=True) or {}
    contact = data.get("contact", "").strip()
    code = data.get("code", "").strip()  # verification code

    if not contact:
        return jsonify({"success": False, "message": "Contact required"}), 400

    users = load_users()
    if contact not in users:
        return jsonify({"success": False, "message": "❌ Account not found"}), 404

    # Step 1: Send code if code not provided
    if not code:
        otp = str(random.randint(100000, 999999))
        users[contact]["pending_code"] = otp
        save_users(users)
        # ⚠ For dev only
        return jsonify({"success": True, "message": "Verification code sent", "debug_code": otp}), 200

    # Step 2: Verify code
    if users[contact].get("pending_code") != code:
        return jsonify({"success": False, "message": "❌ Invalid code"}), 400

    # Delete account
    users.pop(contact)
    save_users(users)
    return jsonify({"success": True, "message": f"Account '{contact}' deleted successfully"}), 200
