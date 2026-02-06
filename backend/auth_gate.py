# backend/user_profile/auth_gate.py
import os
import json
import threading
import random
import hashlib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

# ---------------- MONGO SETUP ----------------
try:
    from backend.db import db
    MONGO_AVAILABLE = True
    users_col = db.get_collection("users")
except Exception:
    MONGO_AVAILABLE = False
    users_col = None

# ---------------- DATA FOLDER / FILE SETUP ----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
file_lock = threading.Lock()

def atomic_write(filepath, data):
    import tempfile, shutil
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)

def load_users_file():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_users_file(users: dict):
    with file_lock:
        atomic_write(USERS_FILE, users)

def save_user_to_file(user_data):
    users = load_users_file()
    users[user_data["contact"]] = user_data
    save_users_file(users)

def get_user_from_file(contact):
    users = load_users_file()
    return users.get(contact)

# ---------------- BLUEPRINT ----------------
auth_bp = Blueprint("auth_bp", __name__)

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
    return now() > time

# ---------------- ROUTES ----------------

# --------- Registration ---------
@auth_bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    full_name = data.get("full_name")
    contact = data.get("contact")
    password = data.get("password")
    confirm = data.get("confirm_password")

    if not all([full_name, contact, password, confirm]):
        return jsonify(success=False, message="All fields required"), 400
    if password != confirm:
        return jsonify(success=False, message="Passwords do not match"), 400

    # Check existing MongoDB
    if MONGO_AVAILABLE and users_col.find_one({"contact": contact}):
        return jsonify(success=False, message="Account already exists"), 400
    # Check file fallback
    if get_user_from_file(contact):
        return jsonify(success=False, message="Account already exists"), 400

    user_data = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal",
        "verified": False,
        "created_at": now().isoformat(),
        "verification": {},
        "history": [],
        "settings": {"theme": "light", "linked_accounts": []},
        "domains": []
    }

    # Save to MongoDB if available
    if MONGO_AVAILABLE:
        users_col.insert_one(user_data)
    # Always save to file
    save_user_to_file(user_data)

    return jsonify(success=True, message="Account created"), 201

# --------- Request Debug Code ---------
@auth_bp.route("/api/request-code", methods=["POST"])
def request_code():
    contact = request.json.get("contact")
    user = users_col.find_one({"contact": contact}) if MONGO_AVAILABLE else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404

    code = generate_code()
    verification_data = {"code": code, "expires": expires_in(10).isoformat()}

    # Update MongoDB
    if MONGO_AVAILABLE:
        users_col.update_one({"contact": contact}, {"$set": {"verification": verification_data}})
    # Update file
    user["verification"] = verification_data
    save_user_to_file(user)

    return jsonify(success=True, debug_code=code), 200

# --------- Verify Account ---------
@auth_bp.route("/api/verify", methods=["POST"])
def verify():
    data = request.json
    contact = data.get("contact")
    code = data.get("code")

    user = users_col.find_one({"contact": contact}) if MONGO_AVAILABLE else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404

    verification = user.get("verification", {})
    if verification.get("code") != code:
        return jsonify(success=False, message="Invalid code"), 400
    if is_expired(datetime.fromisoformat(verification.get("expires"))):
        return jsonify(success=False, message="Code expired"), 400

    # Update verified status
    if MONGO_AVAILABLE:
        users_col.update_one({"contact": contact}, {"$set": {"verified": True}, "$unset": {"verification": ""}})
    user["verified"] = True
    user.pop("verification", None)
    save_user_to_file(user)

    return jsonify(success=True, message="Account verified"), 200

# --------- Login ---------
@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.json
    contact = data.get("contact")
    password = data.get("password")

    user = users_col.find_one({"contact": contact}) if MONGO_AVAILABLE else get_user_from_file(contact)
    if not user:
        return jsonify(success=False, message="Account not found"), 404
    if not user.get("verified"):
        return jsonify(success=False, message="Account not verified"), 403
    if hash_password(password) != user["password"]:
        return jsonify(success=False, message="Invalid password"), 401

    return jsonify(
        success=True,
        contact=user["contact"],
        full_name=user["full_name"],
        role=user.get("role", "normal")
    ), 200
