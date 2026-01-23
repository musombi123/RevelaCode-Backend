from flask import Blueprint, jsonify
from backend.models.models import get_all_users  # inject models for dynamic data
from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017/")["revelacode"]
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

# ---- Optional dynamic endpoints using models.py ----
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
            "role": u["role"],
            "created_at": str(u["created_at"])
        })
    return jsonify({"users": sanitized_users, "total": len(sanitized_users)})
