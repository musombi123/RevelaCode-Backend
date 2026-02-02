# backend/routes/public_routes.py
from flask import Blueprint, jsonify
from pathlib import Path
import importlib.util
import sys
from pymongo import MongoClient

# ----------------------------
# Dynamically load models.py
# ----------------------------
backend_path = Path(__file__).resolve().parent.parent  # /backend
models_path = backend_path / "models" / "models.py"

spec = importlib.util.spec_from_file_location("models", str(models_path))
models = importlib.util.module_from_spec(spec)
sys.modules["models"] = models
spec.loader.exec_module(models)

get_all_users = models.get_all_users

# ----------------------------
# MongoDB setup
# ----------------------------
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["revelacode"]


# ----------------------------
# Blueprint
# ----------------------------
public_bp = Blueprint("public", __name__)

COLLECTIONS = {
    "users": "users"
}

@public_bp.route("/")
def home():
    return jsonify({"message": "Welcome to RevelaCode API"})

@public_bp.route("/info")
def info():
    return jsonify({
        "name": "RevelaCode",
        "version": "1.0",
        "description": "AI-powered Bible & prophecy decoder."
    })

@public_bp.route("/status")
def status():
    return jsonify({"status": "OK"})

@public_bp.route("/users", methods=["GET"])
def list_users():
    """
    Public endpoint to get some user info (e.g., for admin listing)
    You could restrict sensitive info if needed.
    """
    users = get_all_users(db)
    sanitized_users = []
    for u in users:
        sanitized_users.append({
            "username": u["username"],
            "role": u.get("role", "user"),
            "created_at": str(u.get("created_at"))
        })
    return jsonify({"users": sanitized_users, "total": len(sanitized_users)})
