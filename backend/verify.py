# backend/verify.py
import os
import json
import random
import smtplib
from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText
from dotenv import load_dotenv
from datetime import datetime, timedelta

# ------------------ LOAD ENV ------------------
load_dotenv()

# ------------------ BLUEPRINT ------------------
verify_bp = Blueprint("verify", __name__)

# ------------------ PATHS ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")

# ------------------ HELPERS ------------------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def generate_code():
    return str(random.randint(100000, 999999))

def send_email(contact: str, code: str) -> bool:
    """Send verification code via email only"""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not all([host, port, user, password]):
        print("❌ SMTP config missing")
        return False

    try:
        msg = MIMEText(
            f"Your RevelaCode verification code is:\n\n{code}\n\n"
            "This code expires in 10 minutes."
        )
        msg["Subject"] = "RevelaCode Verification Code"
        msg["From"] = user
        msg["To"] = contact

        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        return True
    except Exception as e:
        print("❌ Email send error:", e)
        return False

def send_code_to_contact(contact: str, code: str) -> bool:
    """Wrapper for auth_gate import"""
    return send_email(contact, code)

# ------------------ ROUTES ------------------
@verify_bp.route("/api/verify", methods=["POST"])
def verify_code():
    data = request.get_json(force=True)
    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()

    if not contact or not code:
        return jsonify({"message": "Contact and code required"}), 400

    users = load_users()
    user = users.get(contact)

    if not user:
        return jsonify({"message": "Account not found"}), 404

    if user.get("verified"):
        return jsonify({"message": "Already verified"}), 200

    if user.get("verification_code") != code:
        return jsonify({"message": "Invalid code"}), 400

    if datetime.utcnow() > datetime.fromisoformat(user["code_expires"]):
        return jsonify({"message": "Code expired"}), 400

    user["verified"] = True
    user.pop("verification_code", None)
    user.pop("code_expires", None)
    save_users(users)

    return jsonify({"message": "Account verified successfully"}), 200

# ------------------ TEST ------------------
@verify_bp.route("/api/verify-test", methods=["GET"])
def verify_test():
    return jsonify({"message": "verify_bp email-only is live"}), 200
