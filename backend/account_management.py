# backend/user_profile/accounts.py
import os
import json
import threading
import random
import hashlib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

from .db import users_col  # MongoDB collection

# ---------------- DATA FOLDER SETUP ----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
file_lock = threading.Lock()

# ---------------- BLUEPRINT ----------------
accounts_bp = Blueprint("accounts", __name__)

# ---------------- HELPERS ----------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    return str(random.randint(100000, 999999))

def now():
    return datetime.utcnow()

def expires_in(minutes=10):
    return now() + timedelta(minutes=minutes)

def is_expired(time):
    if not time:
        return True
    if isinstance(time, str):
        time = datetime.fromisoformat(time)
    return now() > time

# ---------------- FILE STORAGE HELPERS ----------------
def sanitize_mongo_doc(doc: dict) -> dict:
    """Convert Mongo ObjectId to string for JSON serialization."""
    if not doc:
        return doc
    doc_copy = doc.copy()
    if "_id" in doc_copy:
        doc_copy["_id"] = str(doc_copy["_id"])
    return doc_copy

def load_users_file():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_users_file(users):
    with file_lock:
        tmp = USERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        os.replace(tmp, USERS_FILE)

def save_user_to_file(user_data):
    users = load_users_file()
    users[user_data["contact"]] = sanitize_mongo_doc(user_data)  # <-- _id safe
    save_users_file(users)

def get_user_from_file(contact):
    users = load_users_file()
    return users.get(contact)

# ---------------- ACCOUNT ROUTES ----------------

# ----- REQUEST PASSWORD RESET -----
@accounts_bp.route("/api/request-reset", methods=["POST"])
def request_reset():
    contact = (request.json or {}).get("contact")
    user = users_col.find_one({"contact": contact}) if users_col else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404

    code = generate_code()
    reset_data = {"code": code, "expires": expires_in(10).isoformat()}

    if users_col:
        users_col.update_one({"contact": contact}, {"$set": {"password_reset": reset_data}})
    else:
        user["password_reset"] = reset_data
        save_user_to_file(user)

    return jsonify(success=True, debug_code=code), 200

# ----- VERIFY RESET CODE -----
@accounts_bp.route("/api/verify-reset", methods=["POST"])
def verify_reset():
    data = request.json or {}
    contact = data.get("contact")
    code = data.get("code")

    user = users_col.find_one({"contact": contact}) if users_col else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404

    reset = user.get("password_reset", {})
    if reset.get("code") != code:
        return jsonify(success=False, message="Invalid code"), 400
    if is_expired(reset.get("expires")):
        return jsonify(success=False, message="Code expired"), 400

    if users_col:
        users_col.update_one({"contact": contact}, {"$set": {"_can_reset": True}})
    else:
        user["_can_reset"] = True
        save_user_to_file(user)

    return jsonify(success=True, message="Code verified, proceed to reset"), 200

# ----- RESET PASSWORD -----
@accounts_bp.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.json or {}
    contact = data.get("contact")
    new_password = data.get("new_password")
    confirm = data.get("confirm_password")

    if not all([contact, new_password, confirm]):
        return jsonify(success=False, message="All fields required"), 400
    if new_password != confirm:
        return jsonify(success=False, message="Passwords do not match"), 400

    user = users_col.find_one({"contact": contact}) if users_col else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404
    if not user.get("_can_reset"):
        return jsonify(success=False, message="Reset not authorized"), 403

    if users_col:
        users_col.update_one(
            {"contact": contact},
            {"$set": {"password": hash_password(new_password)},
             "$unset": {"password_reset": "", "_can_reset": ""}}
        )
    else:
        user["password"] = hash_password(new_password)
        user.pop("password_reset", None)
        user.pop("_can_reset", None)
        save_user_to_file(user)

    return jsonify(success=True, message="Password reset successful"), 200

# ----- REQUEST ACCOUNT DELETE -----
@accounts_bp.route("/api/request-delete", methods=["POST"])
def request_delete():
    contact = (request.json or {}).get("contact")
    user = users_col.find_one({"contact": contact}) if users_col else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404

    code = generate_code()
    delete_data = {"code": code, "expires": expires_in(10).isoformat()}

    if users_col:
        users_col.update_one({"contact": contact}, {"$set": {"delete_verification": delete_data}})
    else:
        user["delete_verification"] = delete_data
        save_user_to_file(user)

    return jsonify(success=True, debug_code=code), 200

# ----- CONFIRM ACCOUNT DELETE -----
@accounts_bp.route("/api/confirm-delete", methods=["POST"])
def confirm_delete():
    data = request.json or {}
    contact = data.get("contact")
    code = data.get("code")

    user = users_col.find_one({"contact": contact}) if users_col else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404

    delete_ver = user.get("delete_verification", {})
    if delete_ver.get("code") != code:
        return jsonify(success=False, message="Invalid code"), 400
    if is_expired(delete_ver.get("expires")):
        return jsonify(success=False, message="Code expired"), 400

    if users_col:
        users_col.delete_one({"contact": contact})
    else:
        users = load_users_file()
        users.pop(contact, None)
        save_users_file(users)

    return jsonify(success=True, message="Account permanently deleted"), 200
