import subprocess
import logging
from datetime import datetime

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# === COMMANDS ===
commands = [
    "python fetch_news.py",
    "python categorize.py",
    "python decode_news.py",
    "python archive_old_events.py"
]

# === RUN PIPELINE ===
def run_pipeline():
    logging.info("🚀 Starting daily news pipeline...")

    for cmd in commands:
        logging.info(f"▶ Running: {cmd}")
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            logging.error(f"❌ Failed: {cmd}")
            break
        else:
            logging.info(f"✅ Completed: {cmd}")

    logging.info("✅ Daily pipeline finished.")

if __name__ == "__main__":
    run_pipeline()
