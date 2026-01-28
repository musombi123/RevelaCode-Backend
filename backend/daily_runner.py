import subprocess
import logging
import os
import time
from datetime import datetime

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

commands = [
    "python fetch_news.py",
    "python categorize.py",
    "python decode_news.py",
    "python archive_old_events.py"
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

        result = subprocess.run(
            cmd,
            shell=True,
            cwd=BASE_DIR
        )

        if result.returncode != 0:
            logger.error(f"❌ Failed: {cmd}")
            return

        logger.info(f"✅ Completed: {cmd}")

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
