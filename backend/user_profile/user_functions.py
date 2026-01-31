# backend/user_data/user_functions.py

from .store import create_user, authenticate
from .user_helpers import save_user_data, load_users, save_users
from datetime import datetime
import hashlib

# ------------------ HELPERS ------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def now_iso():
    return datetime.utcnow().isoformat()

# ------------------ CORE FUNCTIONS ------------------

def register_user(email: str, password: str, full_name: str = "New User"):
    """
    Creates a new user account, auto-verifies using debug code,
    and initializes user history & settings.
    Raises ValueError if user already exists.
    """
    users = load_users()
    if email in users:
        raise ValueError("User already exists")

    # Create user
    users[email] = {
        "full_name": full_name,
        "contact": email,
        "password": hash_password(password),
        "role": "normal",
        "verified": False,
        "created_at": now_iso(),
        "guest_trials": 0
    }

    # Save debug code for verification (auto)
    code = set_user_code(users, email, code_type="verify", minutes=10)
    # Immediately verify user using debug code
    users[email]["verified"] = True
    clear_user_code(users[email], "verify")

    # Persist to file
    save_users(users)

    # Initialize user-specific data
    save_user_data(email, history=[], settings={"theme": "light", "linked_accounts": []})

    return users[email]  # return full user info

def login_user(email: str, password: str):
    """
    Authenticates a user.
    Returns user dict or None.
    """
    user = authenticate(email=email, password=password)
    if not user:
        return None
    # Ensure verified (in case register bypassed)
    if not user.get("verified"):
        user["verified"] = True
        users = load_users()
        users[email] = user
        save_users(users)
    return user
