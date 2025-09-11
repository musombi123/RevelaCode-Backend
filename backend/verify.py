# backend/verify.py
import os, json, random
from flask import Blueprint, request, jsonify

verify_bp = Blueprint("verify", __name__)

USERS_FILE = os.path.join("backend", "user_data", "users.json")

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# --- Send verification code ---
@verify_bp.route("/api/send-code", methods=["POST"])
def send_code():
    try:
        data = request.get_json(force=True)
        contact = data.get("contact", "").strip()

        if not contact:
            return jsonify({"message": "Contact is required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        # generate OTP (6-digit)
        code = str(random.randint(100000, 999999))
        users[contact]["pending_code"] = code
        users[contact]["verified"] = False
        save_users(users)

        # Normally you’d send via email/SMS here
        return jsonify({
            "message": "✅ Verification code generated",
            "debug_code": code  # ⚠️ only for testing, remove in prod!
        }), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# --- Verify code ---
@verify_bp.route("/api/verify-code", methods=["POST"])
def verify_code():
    try:
        data = request.get_json(force=True)
        contact = data.get("contact", "").strip()
        code = data.get("code", "").strip()

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        if users[contact].get("pending_code") != code:
            return jsonify({"message": "❌ Invalid code"}), 400

        users[contact]["verified"] = True
        users[contact].pop("pending_code", None)
        save_users(users)

        return jsonify({"message": "✅ Account verified successfully"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
