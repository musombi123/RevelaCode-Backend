"""Render worker entry point for RevelaCode background jobs.

It deliberately imports no Flask app. The worker owns its own bounded MongoDB
client only when a task needs the database.
"""
import logging
import os
import threading

from backend.background_jobs import start_background_jobs

logger = logging.getLogger("revelacode.background_worker")


def main() -> None:
    if not os.getenv("MONGO_URI", "").strip():
        raise RuntimeError("MONGO_URI must be configured for the background worker")

    start_background_jobs()
    logger.info("RevelaCode background worker is running")
    threading.Event().wait()


if __name__ == "__main__":
    main()
