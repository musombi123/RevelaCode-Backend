import subprocess
import logging
import os
import time
from datetime import datetime
from backend.filter_prophecy_news import filter_prophetic_events
import json
from backend.notifications_service import push_prophecy_event
# ======================================================
# CONFIG
# ======================================================

RUN_HOUR = 2            # 02:00 AM
CHECK_INTERVAL = 60     # seconds
DRY_RUN = False         # True = do not execute commands

LOCK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".daily_runner.lock"
)

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

commands = [
    "python -m backend.fetch_news",
    "python -m backend.filter_prophecy_news",
    "python -m backend.categorize",
    "python -m backend.decode_news",
    "python -m backend.archive_old_events"
]


# ======================================================
# LOGGING
# ======================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger("daily_runner")

# ======================================================
# LOCKING
# ======================================================

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        return False
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

# ======================================================
# PIPELINE
# ======================================================

def run_pipeline():
    logger.info("🚀 Starting daily news pipeline")

    for cmd in commands:
        logger.info(f"▶ Running: {cmd}")

        if DRY_RUN:
            logger.info("🧪 DRY RUN — skipped execution")
            continue

        result = subprocess.run(cmd, shell=True, cwd=BASE_DIR)

        if result.returncode != 0:
            logger.error(f"❌ Failed: {cmd}")
            return

        logger.info(f"✅ Completed: {cmd}")

    # 🔥 NEW: LOAD DATA AFTER FETCH STEP
    try:
        from backend.alert_engine import process_events

        latest_file = sorted(
            [f for f in os.listdir("events") if f.endswith(".json")]
        )[-1]

        with open(os.path.join("events", latest_file), "r") as f:
            raw_events = json.load(f)

        # 🔥 APPLY FILTER HERE
        filtered = filter_prophetic_events(raw_events)

        logger.info(f"🔮 Filtered prophetic events: {len(filtered)}")

        for event in filtered:
            if event.get("prophecy_score", 0) >= 10:
                push_prophecy_event(event)

        # 🚨 SEND TO ALERT ENGINE
        process_events(filtered)

        from backend.prophecy_notifications import (
            push_daily_prophecy_summary
        )

        push_daily_prophecy_summary(filtered)

    except Exception as e:
        logger.error(f"❌ Alert pipeline failed: {e}")

    logger.info("✅ Daily pipeline finished")

# ======================================================
# SCHEDULER LOOP
# ======================================================

def scheduler_loop():
    logger.info("⏰ Daily runner scheduler started")

    last_run_date = None

    while True:
        now = datetime.now()

        if (
            now.hour == RUN_HOUR
            and last_run_date != now.date()
        ):
            if not acquire_lock():
                logger.warning("🔒 Daily runner already executed by another worker")
            else:
                try:
                    run_pipeline()
                    last_run_date = now.date()
                finally:
                    release_lock()

        time.sleep(CHECK_INTERVAL)

# ======================================================
# MANUAL RUN SUPPORT
# ======================================================

if __name__ == "__main__":
    run_pipeline()
