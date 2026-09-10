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
    Determine the actual refresh status returned by
    economic_data_service.

    The economic service stores its refresh state under:

        result["refresh"]["status"]

    Supported states:

        live
        partial
        stale
        failed
        unavailable
        unknown
    """

    # -----------------------------------------------------
    # PRIMARY SOURCE:
    # refresh.status
    # -----------------------------------------------------

    refresh = result.get(
        "refresh"
    )

    if isinstance(
        refresh,
        dict,
    ):

        status = refresh.get(
            "status"
        )

        if isinstance(
            status,
            str,
        ):

            normalized = (
                status
                .strip()
                .lower()
            )

            if normalized:
                return normalized

    # -----------------------------------------------------
    # SECONDARY SOURCE:
    # source_status
    # -----------------------------------------------------

    source_status = result.get(
        "source_status"
    )

    if isinstance(
        source_status,
        str,
    ):

        normalized = (
            source_status
            .strip()
            .lower()
        )

        if normalized in {
            "live",
            "partial",
            "stale",
            "failed",
            "unavailable",
        }:
            return normalized

    # -----------------------------------------------------
    # LEGACY SOURCE:
    # status
    # -----------------------------------------------------

    status = result.get(
        "status"
    )

    if isinstance(
        status,
        str,
    ):

        normalized = (
            status
            .strip()
            .lower()
        )

        if normalized:
            return normalized

    # -----------------------------------------------------
    # NEVER CALL THIS "completed"
    # -----------------------------------------------------

    return "unknown"


# =========================================================
# STATUS DISPLAY
# =========================================================

def _log_status(
    status: str,
) -> None:
    """
    Log the correct message for the refresh state.
    """

    if status == "live":

        logger.info(
            "Economic data refresh completed successfully."
        )

        return

    if status == "partial":

        logger.warning(
            "Economic data refresh completed partially."
        )

        return

    if status == "stale":

        logger.warning(
            "Economic data refresh failed upstream; "
            "latest cached snapshot retained."
        )

        return

    if status in {
        "failed",
        "error",
        "unavailable",
    }:

        logger.error(
            "Economic data refresh failed with status=%s.",
            status,
        )

        return

    logger.warning(
        "Economic data refresh completed with "
        "unrecognized status=%s.",
        status,
    )


# =========================================================
# REFRESH
# =========================================================

def update_economic_data() -> dict:
    """
    Refresh live economic indicators.

    The service is responsible for:

        - obtaining live/up-to-date data
        - validating source responses
        - normalizing the data
        - updating the local cache
        - preserving source metadata
        - handling source failures safely

    This job is responsible for:

        - execution
        - logging
        - status handling
        - CLI-friendly reporting
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

        _log_status(
            status
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

        0 = live refresh
        1 = partial/stale/failed/unavailable/unknown
    """

    result = update_economic_data()

    status = result.get(
        "status",
        "unknown",
    )

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
        f"Status : {status}"
    )

    print(
        f"Started: {result.get('started_at', '-')}"
    )

    print(
        f"Ended  : {result.get('finished_at', '-')}"
    )

    # -----------------------------------------------------
    # SOURCE SUMMARY
    # -----------------------------------------------------

    data = result.get(
        "data"
    )

    if isinstance(
        data,
        dict,
    ):

        refresh = data.get(
            "refresh"
        )

        if isinstance(
            refresh,
            dict,
        ):

            successful = refresh.get(
                "successful_sources",
                [],
            )

            failed = refresh.get(
                "failed_sources",
                [],
            )

            if isinstance(
                successful,
                list,
            ):

                print(
                    f"Successful sources: {len(successful)}"
                )

                for source in successful:

                    print(
                        f"  + {source}"
                    )

            if isinstance(
                failed,
                list,
            ):

                print(
                    f"Failed sources    : {len(failed)}"
                )

                for source in failed:

                    print(
                        f"  - {source}"
                    )

    # -----------------------------------------------------
    # ERROR
    # -----------------------------------------------------

    error = result.get(
        "error"
    )

    if error:

        print(
            f"Error  : {error}"
        )

    print(
        "============================================================"
    )

    # -----------------------------------------------------
    # EXIT CODE
    # -----------------------------------------------------

    if status == "live":
        return 0

    return 1


# =========================================================
# EXECUTION
# =========================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )
