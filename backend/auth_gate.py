# auth_api.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from auth_gate import load_users, save_users, hash_password, get_user_role

app = Flask(__name__)
CORS(app)  # Allow CORS requests from frontend

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    users = load_users()
    hashed = hash_password(password)

    if username in users and users[username]['password'] == hashed:
        role = get_user_role(username)
        return jsonify({"success": True, "username": username, "role": role}), 200
    else:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    users = load_users()
    if username in users:
        return jsonify({"success": False, "message": "Username already exists"}), 409

    users[username] = {
        "password": hash_password(password),
        "role": "normal"  # default role
    }
    save_users(users)
    return jsonify({"success": True, "username": username, "message": "Registration successful"}), 201

@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.get_json()
    username = data.get('username')

    if not username:
        return jsonify({"valid": False, "message": "Username is required"}), 400

    users = load_users()
    if username in users:
        role = get_user_role(username)
        return jsonify({"valid": True, "username": username, "role": role}), 200
    else:
        return jsonify({"valid": False, "message": "User not found"}), 404

# Optional guest route (optional for your frontend)
@app.route('/api/guest', methods=['POST'])
def guest_login():
    return jsonify({"success": True, "role": "guest", "username": "guest_user"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
