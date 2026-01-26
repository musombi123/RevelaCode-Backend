# backend/user_data/user_functions.py
import os, json, tempfile, shutil, logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
USERS_FILE = os.path.join(BASE_DIR, "users.json")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def safe_contact(contact: str) -> str:
    return contact.replace("@", "_at_").replace(".", "_dot_").replace("+", "_plus_")

def atomic_write(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False) as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)
    logging.info(f"Data written atomically to {filepath}")

def load_user_data(contact):
    os.makedirs(DATA_DIR, exist_ok=True)
    safe = safe_contact(contact)
    history_file = os.path.join(DATA_DIR, f"{safe}_history.json")
    settings_file = os.path.join(DATA_DIR, f"{safe}_settings.json")
    try:
        with open(history_file) as f:
            history = json.load(f)
    except:
        history = []
    try:
        with open(settings_file) as f:
            settings = json.load(f)
    except:
        settings = {"theme": "light", "linked_accounts": []}
    return {"history": history, "settings": settings}

def save_user_data(contact, history=None, settings=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    safe = safe_contact(contact)
    if history is not None:
        atomic_write(os.path.join(DATA_DIR, f"{safe}_history.json"), history)
    if settings is not None:
        atomic_write(os.path.join(DATA_DIR, f"{safe}_settings.json"), settings)
