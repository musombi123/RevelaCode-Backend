from datetime import datetime

# Example in-memory users for demo
USERS = [
    {"username": "admin1", "role": "admin"},
    {"username": "support1", "role": "support"},
    {"username": "support2", "role": "support"}
]

def get_user(username):
    """Return user dict if username exists, else None."""
    for user in USERS:
        if user["username"] == username:
            return user
    return None

# MongoDB collection names (for reference)
COLLECTIONS = {
    "users": "users",
    "scriptures": "scriptures",
    "admin_actions": "admin_actions",
    "support_tickets": "support_tickets"
}

# Example function for creating a user (replace with DB logic)
def create_user(db, username, role):
    """Insert a new user into the database."""
    user = {
        "username": username,
        "role": role,
        "created_at": datetime.utcnow()
    }
    db[COLLECTIONS["users"]].insert_one(user)
    return user

# Example function for fetching all users
def get_all_users(db):
    """Fetch all users from the database."""
    return list(db[COLLECTIONS["users"]].find())
