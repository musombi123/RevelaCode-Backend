"""Background job lifecycle, isolated from Flask/Gunicorn web workers.

This module intentionally does not import the Flask application. Render's
worker process can execute the legacy scheduled tasks without registering
HTTP routes, opening unrelated integrations, or loading web-only secrets.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger("revelacode.background_jobs")

_background_jobs_started = False
_background_jobs_lock = threading.Lock()


def maybe_import_sda_q3_2026() -> None:
    """Run the optional SDA importer only when explicitly enabled."""
    enabled = os.getenv("IMPORT_SDA_Q3_2026", "false").strip().casefold()
    if enabled != "true":
        logger.info("SDA Q3 2026 importer disabled")
        return

    try:
        from backend.study.import_sda_q3_2026 import import_q3

        logger.info("Starting SDA Q3 2026 importer")
        result = import_q3()
        if not isinstance(result, dict):
            logger.warning("SDA importer returned an unexpected result type")
            return

        requested = result.get("lessons_requested", 0)
        successful = result.get("successful", 0)
        failed = result.get("failed", 0)
        logger.info(
            "SDA import finished | requested=%s successful=%s failed=%s",
            requested,
            successful,
            failed,
        )
        if failed:
            logger.warning("SDA import completed with failures")
    except Exception:
        logger.exception("SDA Q3 2026 importer failed")


def _sda_importer_thread() -> None:
    thread = threading.Thread(
        target=maybe_import_sda_q3_2026,
        name="SDA-Q3-2026-Importer",
        daemon=True,
    )
    thread.start()
    logger.info("SDA importer thread started")


def _daily_runner_loop() -> None:
    """Run the existing daily pipeline once per day and retry failed runs."""
    last_successful_run_date = None
    logger.info("Daily runner scheduler started")

    while True:
        today = datetime.now().date()
        if last_successful_run_date != today:
            try:
                from backend.daily_runner import run_pipeline

                logger.info("Starting daily news pipeline")
                succeeded = bool(run_pipeline())
                if succeeded:
                    last_successful_run_date = today
                    logger.info("Daily news pipeline completed successfully")
                else:
                    logger.error(
                        "Daily news pipeline returned failure; it will be retried"
                    )
            except Exception:
                logger.exception("Daily news pipeline failed; it will be retried")

        time.sleep(3600)


def start_background_jobs() -> None:
    """Start the legacy job loops once in this worker process."""
    global _background_jobs_started

    with _background_jobs_lock:
        if _background_jobs_started:
            logger.info("Background jobs already started in this process")
            return
        _background_jobs_started = True

    _sda_importer_thread()
    thread = threading.Thread(
        target=_daily_runner_loop,
        name="Daily-Runner",
        daemon=True,
    )
    thread.start()
    logger.info("Daily runner thread started")
