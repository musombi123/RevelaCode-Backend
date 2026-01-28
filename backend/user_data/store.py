import json, os, uuid, threading, hashlib
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)

USERS_FILE = os.path.join(BASE_DIR, "users.json")
INDEX_FILE = os.path.join(BASE_DIR, "auth_index.json")

LOCK = threading.Lock()

def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _atomic_save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ---------------- USERS ---------------- #

def create_user(email, password):
    with LOCK:
        users = _load(USERS_FILE)
        index = _load(INDEX_FILE)

        if email in index:
            raise ValueError("User already exists")

        user_id = str(uuid.uuid4())

        users[user_id] = {
            "id": user_id,
            "email": email,
            "password": hash_password(password),
            "role": "user",
            "created_at": datetime.utcnow().isoformat()
        }

        index[email] = user_id

        _atomic_save(USERS_FILE, users)
        _atomic_save(INDEX_FILE, index)

        return users[user_id]

def authenticate(email, password):
    index = _load(INDEX_FILE)
    users = _load(USERS_FILE)

    user_id = index.get(email)
    if not user_id:
        return None

    user = users.get(user_id)
    if not user:
        return None

    if user["password"] != hash_password(password):
        return None

    return user
