# auth_api.py
from flask import Flask, request, jsonify
from auth_gate import load_users, save_users, hash_password, get_user_role

app = Flask(__name__)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    users = load_users()
    hashed = hash_password(password)
    if username in users and users[username]['password'] == hashed:
        role = get_user_role(username)
        return jsonify({"success": True, "username": username, "role": role})
    else:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    users = load_users()
    if username in users:
        return jsonify({"success": False, "message": "Username already exists"}), 400

    users[username] = {"password": hash_password(password), "role": "normal"}
    save_users(users)
    return jsonify({"success": True, "username": username})

@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.json
    username = data.get('username')
    users = load_users()
    if username in users:
        role = get_user_role(username)
        return jsonify({"valid": True, "username": username, "role": role})
    else:
        return jsonify({"valid": False}), 401

if __name__ == '__main__':
    app.run(debug=True, port=5000)
