# backend/list_users.py
import json
import os

USERS_FILE = './backend/users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def list_users():
    print("=== 👥 List of Registered Users ===")
    users = load_users()

    if not users:
        print("⚠ No users found.")
        return

    for username, info in users.items():
        role = info.get('role', 'normal')
        contact = info.get('contact', 'N/A')
        print(f"- Username: {username} | Role: {role} | Contact: {contact}")

if __name__ == "__main__":
    list_users()
