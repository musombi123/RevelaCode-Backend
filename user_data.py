import json
import os
import tempfile
import shutil
import logging

DATA_DIR = "./backend/user_data"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def atomic_write(filepath, data):
    dirpath = os.path.dirname(filepath)
    with tempfile.NamedTemporaryFile('w', dir=dirpath, delete=False) as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)
    logging.info(f"Data written atomically to {filepath}")

def load_user_data(contact):
    """
    Load user data (history & settings) by contact (email or phone).
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    history_file = os.path.join(DATA_DIR, f"{contact}_history.json")
    settings_file = os.path.join(DATA_DIR, f"{contact}_settings.json")

    try:
        with open(history_file) as f:
            history = json.load(f)
        logging.info(f"Loaded history for user '{contact}'")
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning(f"History file missing or corrupt for user '{contact}', using default")
        history = []

    try:
        with open(settings_file) as f:
            settings = json.load(f)
        logging.info(f"Loaded settings for user '{contact}'")
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning(f"Settings file missing or corrupt for user '{contact}', using default")
        settings = {"theme": "light", "linked_accounts": []}

    return {"history": history, "settings": settings}

def save_user_data(contact, history=None, settings=None):
    """
    Save user data (history & settings) by contact (email or phone).
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    if history is not None:
        history_file = os.path.join(DATA_DIR, f"{contact}_history.json")
        atomic_write(history_file, history)
        logging.info(f"Saved history for user '{contact}'")

    if settings is not None:
        settings_file = os.path.join(DATA_DIR, f"{contact}_settings.json")
        atomic_write(settings_file, settings)
        logging.info(f"Saved settings for user '{contact}'")
