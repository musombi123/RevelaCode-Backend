"""
Jumuiya / Biashara
Economic Intelligence Refresh Job

This job refreshes the live economic data through the
economic_data_service and updates the local cached snapshot.

Run manually:

    python -m backend.jumuiya.biashara.intelligence.jobs.update_economic_data

Or from inside the backend directory:

    python -m jumuiya.biashara.intelligence.jobs.update_economic_data

Recommended production schedule:
    every 1-6 hours depending on the data sources being used.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "jumuiya.biashara.economic_refresh"
)


# =========================================================
# SERVICE IMPORT
# =========================================================

try:
    from backend.jumuiya.biashara.intelligence.services import (
        economic_data_service,
    )

except ImportError as exc:
    logger.error(
        "Unable to import economic_data_service: %s",
        exc,
    )
    raise


# =========================================================
# TIME
# =========================================================

def utc_now_iso() -> str:
    """
    Return the current UTC timestamp in ISO-8601 format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# RESULT HELPERS
# =========================================================

def _as_dict(
    value: Any,
) -> dict:
    """
    Safely convert a service response into a dictionary.
    """

    if isinstance(
        value,
        dict,
    ):
        return value

    return {
        "result": value
    }


def _extract_status(
    result: dict,
) -> str:
    """
    Determine the refresh status from the service response.
    """

    for key in (
        "status",
        "state",
        "result",
    ):
        value = result.get(
            key
        )

        if isinstance(
            value,
            str,
        ):
            return value.lower()

    return "completed"


# =========================================================
# REFRESH
# =========================================================

def update_economic_data() -> dict:
    """
    Refresh live economic indicators.

    The service is responsible for:

        - obtaining live/up-to-date data
        - validating the source response
        - normalizing the data
        - updating the local cache
        - preserving source metadata
        - handling source failures safely
    """

    started_at = utc_now_iso()

    logger.info(
        "Starting economic data refresh."
    )

    refresh_function = getattr(
        economic_data_service,
        "refresh_economic_indicators",
        None,
    )

    if not callable(
        refresh_function
    ):
        raise RuntimeError(
            "economic_data_service.py must expose "
            "refresh_economic_indicators()."
        )

    try:
        raw_result = (
            refresh_function()
        )

        result = _as_dict(
            raw_result
        )

        status = _extract_status(
            result
        )

        finished_at = utc_now_iso()

        response = {
            "job": (
                "jumuiya_biashara_economic_refresh"
            ),
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "data": result,
        }

        if status in {
            "failed",
            "error",
            "unavailable",
        }:
            logger.warning(
                "Economic refresh completed with "
                "status=%s",
                status,
            )
        else:
            logger.info(
                "Economic data refresh completed "
                "successfully."
            )

        return response

    except Exception as exc:
        finished_at = utc_now_iso()

        logger.exception(
            "Economic data refresh failed."
        )

        return {
            "job": (
                "jumuiya_biashara_economic_refresh"
            ),
            "status": "failed",
            "started_at": started_at,
            "finished_at": finished_at,
            "error": str(
                exc
            ),
        }


# =========================================================
# MAIN
# =========================================================

def main() -> int:
    """
    CLI entry point.

    Exit codes:

        0 = refresh succeeded
        1 = refresh failed
    """

    result = update_economic_data()

    print()
    print(
        "============================================================"
    )
    print(
        "JUMUIYA BIASHARA ECONOMIC DATA REFRESH"
    )
    print(
        "============================================================"
    )
    print(
        f"Status : {result.get('status', 'unknown')}"
    )
    print(
        f"Started: {result.get('started_at', '-')}"
    )
    print(
        f"Ended  : {result.get('finished_at', '-')}"
    )
    print(
        "============================================================"
    )

    if result.get(
        "status"
    ) in {
        "failed",
        "error",
        "unavailable",
    }:
        error = result.get(
            "error"
        )

        if error:
            print(
                f"Error  : {error}"
            )

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
