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
    # Each application process owns a bounded pool. Keep these values
    # configurable because total MongoDB connections scale with the number
    # of web/worker processes, not just this single client.
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "10000")),
        connectTimeoutMS=int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "10000")),
        socketTimeoutMS=int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "10000")),
        maxPoolSize=int(os.getenv("MONGO_MAX_POOL_SIZE", "20")),
        minPoolSize=int(os.getenv("MONGO_MIN_POOL_SIZE", "0")),
        maxConnecting=int(os.getenv("MONGO_MAX_CONNECTING", "2")),
        waitQueueTimeoutMS=int(os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "5000")),
        appname=os.getenv("MONGO_APP_NAME", "RevelaCode-Backend"),
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
