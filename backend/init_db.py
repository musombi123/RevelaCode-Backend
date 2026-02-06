# backend/init_db.py
from db import users_col

users_col.create_index("contact", unique=True)
print("✅ Unique index created on contact")
