from flask import Flask, request, jsonify
import json
import os
import hashlib

app = Flask(__name__)
USERS_FILE = "./backend/user_data/users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    contact = data.get('contact')
    password = data.get('password')

    if not contact or not password:
        return jsonify({"message": "❌ Missing fields"}), 400

    users = load_users()

    user = users.get(contact)
    if user and user["password"] == hash_password(password):
        return jsonify({
            "message": "✅ Login successful!",
            "username": contact,
            "full_name": user["full_name"],
            "role": user["role"]
        }), 200

    return jsonify({"message": "❌ Invalid credentials"}), 401

if __name__ == "__main__":
    app.run(debug=True)
