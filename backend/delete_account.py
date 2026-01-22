# backend/delete_account_api.py
import random
from flask import Blueprint, request, jsonify
from backend.verify import load_users, save_users, send_code_to_contact

delete_bp = Blueprint("delete", __name__)

@delete_bp.route("/api/delete-account", methods=["POST"])
def delete_account_api():
    """
    Delete user account with two-step verification:
      1. Generate & send code to contact (phone/email) if code not provided
      2. Verify code and delete account
    """
    try:
        data = request.get_json(force=True) or {}
        contact = data.get("contact", "").strip().lower()
        code = data.get("code", "").strip()

        if not contact:
            return jsonify({"success": False, "message": "❌ Contact is required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"success": False, "message": "❌ Account not found"}), 404

        # Step 1: Send verification code if not provided
        if not code:
            otp = str(random.randint(100000, 999999))
            users[contact]["pending_delete_code"] = otp
            save_users(users)

            # Attempt sending via phone/email
            sent = send_code_to_contact(contact, otp)

            return jsonify({
                "success": True,
                "message": "✅ Verification code sent" if sent else "✅ Verification code generated (debug mode)",
                "sent": sent,
                "debug_code": otp if not sent else None
            }), 200

        # Step 2: Verify code
        if users[contact].get("pending_delete_code") != code:
            return jsonify({"success": False, "message": "❌ Invalid verification code"}), 400

        # Delete account
        users.pop(contact)
        save_users(users)

        return jsonify({
            "success": True,
            "message": f"✅ Account '{contact}' deleted successfully"
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": f"❌ {e}"}), 500
