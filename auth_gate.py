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
    username = input("Choose a unique username: ").strip()
    full_name = input("Enter your full name: ").strip()
    contact = input("Enter phone number or email: ").strip()
    password = input("Choose a password: ").strip()
    confirm_password = input("Confirm password: ").strip()

    if password != confirm_password:
        print("❌ Passwords do not match.")
        return None

    users = load_users()
    if username in users:
        print("⚠ Username already exists. Try a different one.")
        return None

    users[username] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal"
    }
    save_users(users)

    # Create user settings/history
    save_user_data(username, history=[], settings={"theme": "light", "linked_accounts": []})

    print(f"✅ Registration complete. Welcome, {full_name}!")
    return username

def login():
    print("=== RevelaCode Login ===")
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    users = load_users()
    hashed = hash_password(password)

    if username in users and users[username]["password"] == hashed:
        print(f"✅ Login successful. Welcome back, {users[username]['full_name']}!")
        return username
    else:
        print("❌ Invalid username or password.")
        return None

def get_user_role(username):
    users = load_users()
    return users.get(username, {}).get("role", "guest")

def guest_mode():
    print("👤 Continuing in guest mode. Limited access: Bible & decode 5 times per day.")
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
            print("📖 Guest mode: You can read Bible & decode limited prophecies.")
        else:
            role = get_user_role(user)
            data = load_user_data(user)
            print(f"🔓 Logged in as {user} ({role}) — loaded history & settings.")
            if role == "admin":
                print("🛠️ Admin tools unlocked!")
            else:
                print("✨ User tools unlocked!")
    else:
        print("⚠ Could not authenticate. Exiting.")

if __name__ == "__main__":
    main()
