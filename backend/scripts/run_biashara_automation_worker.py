"""Run durable internal Biashara automation dispatch recovery.

Run once from repository root:
    python -m backend.scripts.run_biashara_automation_worker --once

Run as a separate long-lived Render/background worker:
    python -m backend.scripts.run_biashara_automation_worker --continuous --poll-interval 10

This worker creates only internal automation tasks/run records. It does not
send provider messages, mark WooCommerce sync delivered, issue purchases, or
move funds. Configure a dedicated process and monitor dead-letter counts.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time


def main():
    parser = argparse.ArgumentParser(description="Recover durable Biashara internal automation dispatches.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one bounded batch (the default).")
    mode.add_argument("--continuous", action="store_true", help="Poll continuously until stopped.")
    parser.add_argument("--worker-id", help="Stable unique identifier for this worker instance.")
    parser.add_argument("--business-id", help="Optional tenant ID filter, useful for controlled recovery.")
    parser.add_argument("--batch-limit", type=int, default=25, help="Events claimed per batch (1–100).")
    parser.add_argument("--lease-seconds", type=int, default=90, help="Worker lease duration (1–600 seconds).")
    parser.add_argument("--poll-interval", type=float, default=10.0, help="Seconds to sleep between continuous batches (minimum 1).")
    args = parser.parse_args()

    if args.poll_interval < 1:
        parser.error("--poll-interval must be at least 1 second.")

    worker_id = (
        args.worker_id
        or os.getenv("BIASHARA_AUTOMATION_WORKER_ID")
        or f"biashara-worker-{socket.gethostname()}-{os.getpid()}"
    )

    try:
        from backend.jumuiya.biashara.automation.worker import run_dispatch_batch

        while True:
            report = run_dispatch_batch(
                worker_id=worker_id,
                limit=args.batch_limit,
                lease_seconds=args.lease_seconds,
                business_id=args.business_id,
            )
            print(json.dumps(report, sort_keys=True, default=str), flush=True)
            if not args.continuous:
                return 0
            if report.get("no_work"):
                time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print('{"status":"stopped","reason":"keyboard_interrupt"}', flush=True)
        return 0
    except Exception as error:
        print(json.dumps({
            "status": "error",
            "error_type": type(error).__name__,
            "message": str(error),
        }, sort_keys=True), file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
