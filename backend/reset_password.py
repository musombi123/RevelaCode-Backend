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
    contact = input("Enter your phone number or email: ").strip()

    users = load_users()
    user = users.get(contact)

    if not user:
        print("❌ Contact not found.")
        return

    # Send verification code
    request_verification(contact, method='email' if '@' in contact else 'sms')
    submitted = input("Enter the verification code sent to your contact: ").strip()

    if not verify_code(contact, submitted):
        print("❌ Verification failed. Cannot reset password.")
        return

    # Set new password
    new_password = input("Enter your new password: ").strip()
    confirm_password = input("Confirm your new password: ").strip()

    if new_password != confirm_password:
        print("❌ Passwords do not match.")
        return

    users[contact]['password'] = hash_password(new_password)
    save_users(users)
    print(f"✅ Password reset successful for {user['full_name']}!")

if __name__ == "__main__":
    reset_password()
