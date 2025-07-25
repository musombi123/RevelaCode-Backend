import json
import os
import hashlib
from user_data import save_user_data  # optional, keep if you use it for defaults
from auth_gate import load_users, save_users  # reuse common helpers

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
        print("⚠️ This phone/email is already registered. Please login or use another.")
        return

    # save new user
    users[contact] = {
        "full_name": full_name,
        "password": hash_password(password),
        "role": "normal"
    }

    save_users(users)

    # optionally, create default user data (history/settings)
    save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})

    print(f"\n✅ Registration complete! 🎉 Welcome to REVELACODE, {full_name.upper()}")
    print("✨ Where prophecy meets tech in our generation!\n")

if __name__ == "__main__":
    register()
