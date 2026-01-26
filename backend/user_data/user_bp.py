# backend/user_data/user_bp.py
from flask import Blueprint, request, jsonify
import json, os, tempfile, shutil, logging

user_bp = Blueprint("user", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR
USERS_FILE = os.path.join(BASE_DIR, "users.json")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# --- rest of your helpers and routes here ---
