# data/__init__.py
import os
import json
import threading
from datetime import datetime
import tempfile
import shutil

# ----------------------------
# Thread-safe file operations
# ----------------------------
file_lock = threading.Lock()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def atomic_write(filepath, data):
    """Write data atomically to avoid corruption."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)

def load_json_file(filepath):
    """Load JSON safely, return empty dict if missing or invalid."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json_file(filepath, data):
    """Thread-safe save to JSON file."""
    with file_lock:
        atomic_write(filepath, data)

def ensure_data_dir(dirname=""):
    """Ensure data folder exists, optionally return subfolder path."""
    path = os.path.join(BASE_DIR, dirname) if dirname else BASE_DIR
    os.makedirs(path, exist_ok=True)
    return path

def timestamp():
    """Return current UTC timestamp as ISO string."""
    return datetime.utcnow().isoformat()
