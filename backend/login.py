# backend/login.py
import json
import os
import hashlib

USERS_FILE = './backend/users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_user():
    print("=== 🔑 Login ===")
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    users = load_users()
    hashed = hash_password(password)

    if username in users and users[username]['password'] == hashed:
        role = users[username].get('role', 'normal')
        print(f"✅ Login successful! Welcome back, {username}. Your role: {role}")
        return username, role
    else:
        print("❌ Invalid username or password.")
        return None, None

def guest_mode():
    print("👤 Continuing as guest: limited access (Bible only).")
    return "guest", "guest"

def main():
    print("=== RevelaCode Login ===")
    print("[l] Login  |  [g] Continue as guest")
    choice = input("Choose option: ").strip().lower()

    if choice == 'l':
        user, role = login_user()
    elif choice == 'g':
        user, role = guest_mode()
    else:
        print("⚠ Invalid choice. Exiting.")
        return

    if user:
        print(f"🔓 Logged in as: {user} (role: {role})")
        # Here you can load history, settings, etc.
    else:
        print("❌ Login failed.")

if __name__ == "__main__":
    main()
