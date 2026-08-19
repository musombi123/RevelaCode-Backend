from pymongo import MongoClient, ASCENDING, DESCENDING
from jumuiya.config import MONGO_URI, MONGO_DB_NAME

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is not None:
        return _db
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI/MONGODB_URI is not configured.")
    _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
    _db = _client[MONGO_DB_NAME]
    _client.admin.command("ping")
    return _db

def collection(name):
    return get_db()[name]

def ensure_indexes():
    db = get_db()
    db["jumuiya_businesses"].create_index([("owner_user_id", ASCENDING)], unique=True)
    db["jumuiya_businesses"].create_index([("slug", ASCENDING)], unique=True)
    db["jumuiya_products"].create_index([("business_id", ASCENDING), ("status", ASCENDING)])
    db["jumuiya_customers"].create_index([("business_id", ASCENDING), ("created_at", DESCENDING)])
    db["jumuiya_orders"].create_index([("business_id", ASCENDING), ("created_at", DESCENDING)])
    db["jumuiya_sales"].create_index([("business_id", ASCENDING), ("sold_at", DESCENDING)])
    db["jumuiya_expenses"].create_index([("business_id", ASCENDING), ("spent_at", DESCENDING)])
    db["jumuiya_inventory_movements"].create_index(
        [("business_id", ASCENDING), ("product_id", ASCENDING), ("created_at", DESCENDING)]
    )
