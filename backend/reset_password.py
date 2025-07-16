# backend/reset_password.py
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

def reset_password():
    print("=== 🔒 Reset Password ===")
    username = input("Enter your username: ").strip()

    users = load_users()
    user = users.get(username)

    if not user:
        print("❌ Username not found.")
        return

    contact = user.get('contact')
    if not contact:
        print("⚠ No contact info on file for verification.")
        return

    # Send verification code
    request_verification(contact, method='email' if '@' in contact else 'sms')
    submitted = input("Enter the verification code sent to your contact: ").strip()

    if not verify_code(contact, submitted):
        print("❌ Verification failed. Cannot reset password.")
        return

    # Set new password
    new_password = input("Enter your new password: ").strip()
    users[username]['password'] = hash_password(new_password)
    save_users(users)
    print(f"✅ Password reset successful for {username}!")

if __name__ == "__main__":
    reset_password()
