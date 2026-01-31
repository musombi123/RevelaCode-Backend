# test_register_debug.py
import os
from flask import Flask, request, jsonify
from backend.auth_gate import api_register, load_users
from backend.user_data.user_helpers import save_user_data

app = Flask(__name__)

# Wrap your existing register function for testing
@app.route("/test/register", methods=["POST"])
def test_register():
    """
    1) Call your real /api/register logic
    2) Return the saved user data from users.json
    """
    # Simulate request JSON
    data = request.get_json(silent=True) or {}
    # Expect: full_name, contact, password, confirm_password
    required_fields = ["full_name", "contact", "password", "confirm_password"]
    for f in required_fields:
        if f not in data:
            return jsonify({"status": "fail", "message": f"Missing field: {f}"}), 400

    # Call your existing registration logic
    with app.test_request_context(json=data):
        resp = api_register()  # uses your auth_gate api_register directly
        status_code = resp[1] if isinstance(resp, tuple) else 200

    # Now load the user from users.json
    contact = data.get("contact")
    users = load_users()
    user_data = users.get(contact, None)

    if user_data is None:
        return jsonify({"status": "fail", "message": "User not saved"}), 500

    return jsonify({
        "status": "success",
        "message": f"User registered and saved",
        "saved_user": user_data
    }), status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
