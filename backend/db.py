# backend/db.py
from pymongo import MongoClient
import os
import logging

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set")

try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=60000,
        connectTimeoutMS=60000,
        socketTimeoutMS=60000,
        tls=True
    )

    # Force connection now
    client.admin.command("ping")

    db = client.get_default_database()
    logger.info("Connected to MongoDB")

except Exception as e:
    logger.warning(f"MongoDB not available, running without DB: {e}")
    client = None
    db = None

# <<< Add this >>>
def get_db():
    if db is None:
        raise RuntimeError("Database not initialized")
    return db
