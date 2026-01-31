# tester_routes.py
import os
import smtplib
from email.mime.text import MIMEText
from flask import Flask, request, jsonify
from backend.auth_gate import hash_password, set_user_code, save_users, load_users
from backend.user_data.user_helpers import save_user_data

app = Flask(__name__)

# ---------------- ENV ----------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


# ---------------- HELPERS ----------------
def send_email(to_email, subject, body):
    """Send email via SMTP, with full logging."""
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        if SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)

        server.set_debuglevel(1)  # <- VERY VERBOSE
        if SMTP_USE_TLS and not SMTP_USE_SSL:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        return True, "Email sent"
    except Exception as e:
        return False, str(e)


# ---------------- TESTER ROUTE ----------------
@app.route("/test/register-send", methods=["POST"])
def test_register_send():
    """
    1) Create dummy user
    2) Generate verification code
    3) Try sending via SMTP
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email") or "tester123@example.com"

    users = load_users()
    if email in users:
        return jsonify({"status": "fail", "message": "User already exists"}), 400

    # Step 1: Register user
    users[email] = {
        "full_name": "Tester",
        "contact": email,
        "password": hash_password("password123"),
        "role": "normal",
        "verified": False,
        "created_at": "TEST",
    }
    save_users(users)
    save_user_data(email, history=[], settings={"theme": "light", "linked_accounts": []})

    # Step 2: Generate code
    code = set_user_code(users, email, "verify")
    save_users(users)

    # Step 3: Send email
    subject = "Render SMTP Test Code"
    body = f"Your verification code: {code}"
    success, msg = send_email(email, subject, body)

    return jsonify({
        "status": "success" if success else "fail",
        "email": email,
        "debug_code": code,
        "smtp_result": msg
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
