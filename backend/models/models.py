from datetime import datetime
# MongoDB collection names (for reference)
COLLECTIONS = {
    "users": "users",
    "scriptures": "scriptures",
    "admin_actions": "admin_actions",
    "support_tickets": "support_tickets"
}

# Example function for creating a user (replace with DB logic)
def create_user(db, full_name, contact, role, verified=False):
    user = {
        "full_name": full_name,
        "contact": contact,
        "role": role,
        "verified": verified,
        "created_at": datetime.utcnow().isoformat()
    }

    db[COLLECTIONS["users"]].insert_one(user)
    return user

# Example function for fetching all users
def get_all_users(db):
    """Fetch all users from the database."""
    return list(db[COLLECTIONS["users"]].find())
