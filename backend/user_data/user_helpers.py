import os
import json
import tempfile
import shutil
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
file_lock = threading.Lock()


def atomic_write(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)


def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_users(users: dict):
    with file_lock:
        atomic_write(USERS_FILE, users)


def save_user_data(contact, history=None, settings=None):
    users = load_users()
    if contact not in users:
        users[contact] = {"contact": contact, "history": [], "settings": {"theme": "light", "linked_accounts": []}}

    if history is not None:
        users[contact]["history"] = history
    if settings is not None:
        users[contact]["settings"] = settings

    save_users(users)


def load_user_data(contact):
    users = load_users()
    user = users.get(contact, {})
    return {
        "history": user.get("history", []),
        "settings": user.get("settings", {"theme": "light", "linked_accounts": []})
    }
