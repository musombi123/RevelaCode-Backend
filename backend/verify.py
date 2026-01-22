import os, json, random
from flask import Blueprint, request, jsonify

verify_bp = Blueprint("verify", __name__)

USERS_FILE = os.path.join("backend", "user_data", "users.json")

# ------------------ OPTIONAL IMPORTS ------------------
twilio_available = True
try:
    from twilio.rest import Client
except Exception:
    twilio_available = False


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def send_sms(contact: str, code: str):
    """
    Send OTP via SMS using Twilio.
    If Twilio not configured, return False.
    """
    if not twilio_available:
        return False

    sid = os.environ.get("TWILIO_SID")
    auth = os.environ.get("TWILIO_AUTH")
    number = os.environ.get("TWILIO_NUMBER")

    if not sid or not auth or not number:
        return False

    try:
        client = Client(sid, auth)
        client.messages.create(
            body=f"RevelaCode verification code: {code}",
            from_=number,
            to=contact
        )
        return True
    except Exception:
        return False


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

        code = str(random.randint(100000, 999999))
        users[contact]["pending_code"] = code
        users[contact]["verified"] = False
        save_users(users)

        # try send sms/email (sms only for now)
        sent = send_sms(contact, code)

        return jsonify({
            "message": "✅ Verification code sent" if sent else "✅ Verification code generated (debug mode)",
            "sent": sent,
            "debug_code": code if not sent else None
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
