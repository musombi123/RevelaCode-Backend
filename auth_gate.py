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

def register_user(username, password, contact):
    users = load_users()
    if username in users:
        print("⚠ Username already exists.")
        return False
    users[username] = {
        "password": hash_password(password),
        "contact": contact,
        "role": "normal"
    }
    save_users(users)
    # create default settings & history
    save_user_data(username, history=[], settings={"theme": "light"})
    print(f"✅ User '{username}' registered successfully.")
    return True

def login_user(username, password):
    users = load_users()
    hashed = hash_password(password)
    user = users.get(username)
    if user and user["password"] == hashed:
        print(f"✅ Login successful. Welcome {username}!")
        return True
    else:
        print("❌ Invalid username or password.")
        return False

def get_user_role(username):
    users = load_users()
    return users.get(username, {}).get("role", "guest")

if __name__ == "__main__":
    print("=== Auth Gate ===")
    print("[1] Register")
    print("[2] Login")
    choice = input("Choose an option: ").strip()

    if choice == "1":
        username = input("Username: ").strip()
        contact = input("Phone or email: ").strip()
        password = input("Password: ").strip()
        confirm = input("Confirm password: ").strip()
        if password != confirm:
            print("⚠ Passwords do not match.")
        else:
            register_user(username, password, contact)
    elif choice == "2":
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        login_user(username, password)
    else:
        print("Unknown option.")
