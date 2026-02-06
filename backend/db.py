# backend/db.py
import os
import logging
from pymongo import MongoClient, errors
from dotenv import load_dotenv

load_dotenv()

# ---------------------------- LOGGING ----------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------- ENV ----------------------------
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME", "revelacode")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set in environment variables")

# ---------------------------- MONGO CONNECTION ----------------------------
try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=10000,
    )
    # Force immediate connection
    client.admin.command("ping")

    db = client[DB_NAME]

    logger.info("✅ MongoDB connected successfully")

except errors.PyMongoError as e:
    logger.critical(f"❌ MongoDB connection failed: {e}")
    raise RuntimeError("Database initialization failed") from e

# ---------------------------- COLLECTIONS ----------------------------
# Ensure all collections exist
def get_or_create_collection(name):
    if name in db.list_collection_names():
        return db[name]
    else:
        logger.info(f"⚡ Creating collection '{name}'")
        return db.create_collection(name)

users_col = get_or_create_collection("users")
scriptures_col = get_or_create_collection("scriptures")
admin_actions_col = get_or_create_collection("admin_actions")
support_tickets_col = get_or_create_collection("support_tickets")
legal_docs_col = get_or_create_collection("legaldocs")
notifications_col = get_or_create_collection("notifications")
domains_col = get_or_create_collection("domains")  # for domain-specific data

# ---------------------------- HELPERS ----------------------------
def get_db():
    """Return active MongoDB database instance"""
    return db
