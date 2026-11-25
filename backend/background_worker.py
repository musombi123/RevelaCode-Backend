"""Dedicated process for legacy scheduled/background loops.

The web application must not start these threads at import time: Gunicorn
loads the Flask module in each worker process. This module is the single
Render worker entry point for the existing SDA importer and daily runner.
"""
import logging
import threading

from main import start_background_jobs

logger = logging.getLogger("revelacode.background_worker")


def main() -> None:
    start_background_jobs()
    logger.info("RevelaCode background worker is running")
    # Keep the worker process alive while its managed daemon threads run.
    threading.Event().wait()


if __name__ == "__main__":
    main()
