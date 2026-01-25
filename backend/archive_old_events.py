# backend/archive_service.py
import os
import shutil
from datetime import datetime
import json
from flask import Blueprint, jsonify, current_app

archive_bp = Blueprint("archive", __name__)

# === CONFIG ===
EVENTS_DIR = './events'
ARCHIVED_DIR = './archived'
LOG_FILE = os.path.join(ARCHIVED_DIR, 'archive_log.json')

# Ensure directories exist
os.makedirs(ARCHIVED_DIR, exist_ok=True)


# === ARCHIVE LOG ===
def log_archive(filename):
    log_entry = {
        "filename": filename,
        "archived_at": datetime.now().isoformat()
    }

    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
    else:
        log_data = []

    log_data.append(log_entry)

    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# === ARCHIVING ===
def archive_old_events():
    archived_files = []
    for filename in os.listdir(EVENTS_DIR):
        if filename.startswith('events_') and filename.endswith('.json'):
            date_str = filename.replace('events_', '').replace('.json', '')

            # Support multiple date formats
            for fmt in ("%Y-%m-%d", "%Y_%m_%d"):
                try:
                    file_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                current_app.logger.warning(f"Skipping invalid date file: {filename}")
                continue

            if (datetime.now() - file_date).days > 7:
                src = os.path.join(EVENTS_DIR, filename)
                dst = os.path.join(ARCHIVED_DIR, filename)
                shutil.move(src, dst)
                log_archive(filename)
                archived_files.append(filename)
                current_app.logger.info(f"Archived: {filename}")
    return archived_files


# === API ENDPOINTS ===

@archive_bp.route("/api/archive/log", methods=["GET"])
def get_archive_log():
    """
    Fetch archive log (no email required)
    """
    if not os.path.exists(LOG_FILE):
        return jsonify({"status": "ok", "message": "No archived events yet.", "log": []}), 200

    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({"status": "ok", "message": f"{len(data)} archived events found.", "log": data}), 200
    except Exception as e:
        current_app.logger.error(f"Error reading archive log: {str(e)}")
        return jsonify({"status": "error", "message": str(e), "log": []}), 500


@archive_bp.route("/api/archive/run", methods=["POST"])
def run_archive():
    """
    Manually trigger archiving old events
    """
    try:
        archived = archive_old_events()
        return jsonify({
            "status": "ok",
            "message": f"Archived {len(archived)} old events.",
            "archived_files": archived
        }), 200
    except Exception as e:
        current_app.logger.error(f"Error running archive: {str(e)}")
        return jsonify({"status": "error", "message": str(e), "archived_files": []}), 500
