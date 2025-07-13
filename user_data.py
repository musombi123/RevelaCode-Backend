import json
import os

DATA_DIR = "./backend/user_data"

def load_user_data(username):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    history_file = f"{DATA_DIR}/{username}_history.json"
    settings_file = f"{DATA_DIR}/{username}_settings.json"

    if os.path.exists(history_file):
        with open(history_file) as f:
            history = json.load(f)
    else:
        history = []

    if os.path.exists(settings_file):
        with open(settings_file) as f:
            settings = json.load(f)
    else:
        settings = {"theme": "light", "linked_accounts": []}

    return {"history": history, "settings": settings}

def save_user_data(username, history=None, settings=None):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    if history is not None:
        history_file = f"{DATA_DIR}/{username}_history.json"
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

    if settings is not None:
        settings_file = f"{DATA_DIR}/{username}_settings.json"
        with open(settings_file, "w") as f:
            json.dump(settings, f, indent=2)
