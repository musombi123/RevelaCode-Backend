# backend/register.py
import json
import os
import hashlib
from verify import request_verification, verify_code

USERS_FILE = './backend/users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user():
    print("=== ✨ Create New Account ===")
    username = input("Choose username: ").strip()
    password = input("Choose password: ").strip()
    destination = input("Enter email or phone for verification: ").strip()

    users = load_users()
    if username in users:
        print("⚠ Username already exists.")
        return

    # Send code
    request_verification(destination, method='email' if '@' in destination else 'sms')
    submitted = input("Enter the verification code you received: ").strip()

    if not verify_code(destination, submitted):
        print("❌ Verification failed. Cannot create account.")
        return

    # Save user
    users[username] = {
        "password": hash_password(password),
        "contact": destination,
        "role": "normal"
    }
    save_users(users)
    print(f"✅ Account created! Welcome, {username}")

if __name__ == "__main__":
    register_user()
