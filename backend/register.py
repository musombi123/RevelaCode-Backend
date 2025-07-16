import json
import os
import hashlib
from user_data import save_user_data  # Make sure correct path if inside backend/
from auth_gate import load_users, save_users  # reuse if you have these

USERS_FILE = "./backend/users.json"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register():
    print("=== 📜 RevelaCode Registration ===")

    full_name = input("Full name: ").strip()
    contact = input("Phone number or email: ").strip()
    password = input("Choose a password: ").strip()
    confirm_password = input("Confirm password: ").strip()

    if password != confirm_password:
        print("❌ Passwords do not match. Try again.")
        return

    users = load_users() if os.path.exists(USERS_FILE) else {}

    if contact in users:
        print("⚠️ Contact already registered. Please login or use another.")
        return

    users[contact] = {
        "full_name": full_name,
        "password": hash_password(password),
        "role": "normal"
    }

    save_users(users)

    print(f"\n✅ Registration complete! 🎉 Welcome to REVELACODE, {full_name.upper()}")
    print("✨ Where prophecy meets tech in our generation!\n")

if __name__ == "__main__":
    register()
