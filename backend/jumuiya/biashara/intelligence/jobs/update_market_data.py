# backend/jumuiya/biashara/intelligence/jobs/update_market_data.py

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
    "jumuiya.biashara.market_refresh"
)


# =========================================================
# SERVICE
# =========================================================

try:
    from backend.jumuiya.biashara.intelligence.services import (
        market_data_service,
    )

except ImportError as exc:
    logger.error(
        "Unable to import market_data_service: %s",
        exc,
    )
    raise


# =========================================================
# TIME
# =========================================================

def utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# HELPERS
# =========================================================

def _as_dict(
    value: Any,
) -> dict:
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
        ) and status.strip():

            return status.strip().lower()

    source_status = result.get(
        "source_status"
    )

    if isinstance(
        source_status,
        str,
    ) and source_status.strip():

        return source_status.strip().lower()

    status = result.get(
        "status"
    )

    if isinstance(
        status,
        str,
    ) and status.strip():

        return status.strip().lower()

    return "unknown"


def _log_sources(
    result: dict,
) -> None:
    refresh = result.get(
        "refresh"
    )

    if not isinstance(
        refresh,
        dict,
    ):
        return

    successful = refresh.get(
        "successful_sources",
        [],
    )

    failed = refresh.get(
        "failed_sources",
        [],
    )

    logger.info(
        "Successful sources: %s",
        successful,
    )

    if failed:
        logger.warning(
            "Failed sources: %s",
            failed,
        )


# =========================================================
# REFRESH
# =========================================================

def update_market_data() -> dict:
    """
    Execute one live market-data refresh.

    The market_data_service is responsible for:
        - fetching official sources
        - parsing responses
        - validation
        - normalization
        - cache update
        - freshness handling

    This job is responsible for:
        - scheduled execution
        - logging
        - status handling
        - exit result
    """

    started_at = utc_now_iso()

    logger.info(
        "=================================================="
    )

    logger.info(
        "Starting automatic Biashara market-data refresh."
    )

    refresh_function = getattr(
        market_data_service,
        "refresh_market_data",
        None,
    )

    if not callable(
        refresh_function
    ):
        raise RuntimeError(
            "market_data_service.py must expose "
            "refresh_market_data()."
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
                "jumuiya_biashara_market_refresh"
            ),
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "data": result,
        }

        _log_sources(
            result
        )

        if status == "live":

            logger.info(
                "✅ Market data refresh completed successfully."
            )

        elif status == "partial":

            logger.warning(
                "⚠️ Market data refresh completed partially."
            )

        elif status == "stale":

            logger.warning(
                "⚠️ Market data is stale; "
                "latest usable snapshot retained."
            )

        else:

            logger.error(
                "❌ Market data refresh ended with status=%s",
                status,
            )

        logger.info(
            "Finished automatic market-data refresh."
        )

        logger.info(
            "=================================================="
        )

        return response

    except Exception as exc:

        finished_at = utc_now_iso()

        logger.exception(
            "❌ Market data refresh failed."
        )

        return {
            "job": (
                "jumuiya_biashara_market_refresh"
            ),
            "status": "failed",
            "started_at": started_at,
            "finished_at": finished_at,
            "error": str(exc),
        }


# =========================================================
# CLI
# =========================================================

def main() -> int:
    result = update_market_data()

    status = result.get(
        "status",
        "unknown",
    )

    print()
    print(
        "============================================================"
    )
    print(
        "JUMUIYA BIASHARA MARKET DATA REFRESH"
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

            print(
                f"Successful sources: {len(successful)}"
            )

            for source in successful:
                print(
                    f"  + {source}"
                )

            print(
                f"Failed sources    : {len(failed)}"
            )

            for source in failed:
                print(
                    f"  - {source}"
                )

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

    if status == "live":
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )