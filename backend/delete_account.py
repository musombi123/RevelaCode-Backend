# backend/delete_account.py
import json
import os
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

def delete_account():
    print("=== 🗑️ Delete Account ===")
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
        print("❌ Verification failed. Cannot delete account.")
        return

    # Delete user
    del users[username]
    save_users(users)
    print(f"✅ Account '{username}' deleted successfully!")

if __name__ == "__main__":
    delete_account()
