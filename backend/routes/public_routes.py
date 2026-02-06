from flask import Blueprint, jsonify
import os

from backend.db import get_db
from backend.models.models import get_all_users

public_bp = Blueprint("public", __name__)

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
    try:
        db = get_db()
        users = get_all_users(db)

        sanitized = [{
            "id": str(u["_id"]),
            "username": u.get("username"),
            "role": u.get("role", "user"),
            "created_at": str(u.get("created_at"))
        } for u in users]


        return jsonify({
            "users": sanitized,
            "total": len(sanitized)
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "User service unavailable"
        }), 503
