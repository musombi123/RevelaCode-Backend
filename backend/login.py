import json
import os
import hashlib
from user_data import load_user_data

USERS_FILE = "./backend/users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login():
    print("=== 🔑 RevelaCode Login ===")
    contact = input("Enter your phone number or email: ").strip()
    password = input("Password: ").strip()

    users = load_users()
    hashed = hash_password(password)

    user = users.get(contact)
    if user and user["password"] == hashed:
        print(f"✅ Login successful. Welcome back, {user['full_name']}!")
        print(f"🔒 Role: {user.get('role', 'normal')}")
        # Load user data
        data = load_user_data(contact)
        print(f"📜 Loaded history: {len(data['history'])} items.")
        return contact
    else:
        print("❌ Invalid contact or password. Please try again.")
        return None

if __name__ == "__main__":
    login()
