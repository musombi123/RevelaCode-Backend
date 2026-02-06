# backend/migrate_users.py
import json
import os
from datetime import datetime
from db import users_col

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # backend/
PROJECT_ROOT = os.path.dirname(BASE_DIR)               # project root
USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")

if not os.path.exists(USERS_FILE):
    raise RuntimeError(f"users.json not found at {USERS_FILE}")

with open(USERS_FILE, "r", encoding="utf-8") as f:
    users = json.load(f)

count = 0
for contact, user in users.items():
    users_col.update_one(
        {"contact": contact},
        {"$setOnInsert": {
            "contact": contact,
            "full_name": user.get("full_name"),
            "password": user.get("password"),
            "role": user.get("role", "normal"),
            "verified": user.get("verified", False),
            "created_at": datetime.fromisoformat(user["created_at"]),
            "history": user.get("history", []),
            "settings": user.get("settings", {}),
        }},
        upsert=True
    )
    count += 1

print(f"✅ Migrated {count} users to MongoDB")
