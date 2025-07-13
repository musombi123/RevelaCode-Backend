import json
import os
import hashlib
from user_data import load_user_data, save_user_data

USERS_FILE = "./backend/users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register():
    print("=== RevelaCode Registration ===")
    username = input("Choose a username: ").strip()
    password = input("Choose a password: ").strip()

    users = load_users()
    if username in users:
        print("⚠ Username already exists. Try a different one.")
        return None

    users[username] = {"password": hash_password(password), "role": "normal"}
    save_users(users)

    print(f"✅ Registration complete. Welcome, {username}!")
    return username

def login():
    print("=== RevelaCode Login ===")
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    users = load_users()
    hashed = hash_password(password)

    if username in users and users[username]["password"] == hashed:
        print(f"✅ Login successful. Welcome back, {username}!")
        return username
    else:
        print("❌ Invalid username or password.")
        return None

def get_user_role(username):
    users = load_users()
    return users.get(username, {}).get("role", "guest")

def guest_mode():
    print("👤 Continuing in guest mode. Limited access: Bible reading only.")
    return "guest"

def main():
    print("=== RevelaCode Login Gate ===")
    print("[l] Login   [r] Register   [g] Continue as guest")
    choice = input("Your choice: ").strip().lower()

    if choice == "l":
        user = login()
    elif choice == "r":
        user = register()
    elif choice == "g":
        user = guest_mode()
    else:
        print("❓ Invalid choice. Exiting.")
        return

    if user:
        if user == "guest":
            print("📖 Guest mode: You can now read the Bible freely!")
        else:
            role = get_user_role(user)
            data = load_user_data(user)
            print(f"🔓 Logged in as {user} ({role}) — loaded history & settings.")
            if role == "admin":
                print("🛠️ Admin tools unlocked!")
            else:
                print("✨ User tools unlocked!")
            # 🚀 Here, you can launch decoding, news etc.
    else:
        print("⚠ Could not authenticate. Exiting.")

if __name__ == "__main__":
    main()
