"""
Live Kenya Economic Data Service

Jumuiya / Biashara Intelligence

Architecture:

    Trusted public sources
            ↓
    Fetch + validate + normalize
            ↓
    Local JSON cache
            ↓
    Biashara Intelligence API

The cache is only a fallback snapshot.

It is NOT treated as the source of truth.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


# =========================================================
# LOGGING
# =========================================================

LOGGER = logging.getLogger(
    __name__
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_DIR = (
    BASE_DIR
    / "data"
)

CACHE_FILE = (
    DATA_DIR
    / "economic_indicators.json"
)


# =========================================================
# CONFIGURATION
# =========================================================

REQUEST_TIMEOUT = int(
    os.getenv(
        "JUMUIYA_ECONOMIC_TIMEOUT",
        "20",
    )
)

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; "
    "RevelaCode-Jumuiya-EconomicBot/2.0; "
    "+https://revelacode-frontend.onrender.com/)"
)


# =========================================================
# OFFICIAL SOURCES
# =========================================================

CBK_MONETARY_POLICY_URL = (
    "https://www.centralbank.go.ke/monetary-policy/"
)

CBK_FOREX_URL = (
    "https://www.centralbank.go.ke/"
    "rates/forex-exchange-rates/"
)

CBK_INFLATION_URL = (
    "https://www.centralbank.go.ke/"
    "inflation-rates/"
)

KNBS_ECONOMIC_SURVEY_URL = (
    "https://www.knbs.or.ke/"
    "reports/2026-economic-survey/"
)

KNBS_CPI_URL = (
    "https://www.knbs.or.ke/"
    "reports/consumer-price-indices-and-inflation-rates-august-2026/"
)


# =========================================================
# ERRORS
# =========================================================

class EconomicDataError(
    RuntimeError
):
    """Raised when a live economic source cannot be read."""


# =========================================================
# TIME
# =========================================================

def now_iso() -> str:
    """
    Return current UTC time in ISO-8601 format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# NUMERIC HELPERS
# =========================================================

def safe_float(
    value: Any,
) -> float | None:
    """
    Convert a value to float safely.
    """

    if value is None:
        return None

    try:

        cleaned = (
            str(value)
            .replace(",", "")
            .replace("%", "")
            .strip()
        )

        return float(
            cleaned
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# =========================================================
# TLS
# =========================================================

def _verify_setting():
    """
    Return the preferred certificate bundle.

    certifi is used when available.
    Otherwise requests falls back to its normal
    certificate verification behavior.
    """

    if certifi is not None:

        return certifi.where()

    return True


def _insecure_tls_enabled() -> bool:
    """
    Development-only TLS override.

    Enable only in environments where the upstream
    certificate chain cannot be validated, such as the
    current Codespaces environment.

    Production should NEVER enable this.
    """

    return (
        os.getenv(
            "JUMUIYA_ECONOMIC_ALLOW_INSECURE_TLS",
            "false",
        )
        .strip()
        .lower()
        in {
            "true",
            "1",
            "yes",
        }
    )


# =========================================================
# HTTP
# =========================================================

def fetch_url(
    url: str,
) -> str:
    """
    Fetch a trusted public source.

    TLS verification is enabled by default.

    Development-only override:

        JUMUIYA_ECONOMIC_ALLOW_INSECURE_TLS=true

    This allows the service to work around a broken CA
    chain in development environments.

    Never use the insecure setting in production.
    """

    if requests is None:

        raise EconomicDataError(
            "The requests package is not installed."
        )

    insecure_tls = (
        _insecure_tls_enabled()
    )

    verify = (
        False
        if insecure_tls
        else _verify_setting()
    )

    LOGGER.info(
        "Fetching economic source: %s | "
        "TLS verification=%s",
        url,
        verify,
    )

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/pdf"
                ),
            },
            timeout=REQUEST_TIMEOUT,
            verify=verify,
            allow_redirects=True,
        )

        response.raise_for_status()

        return response.text

    except requests.exceptions.SSLError as exc:

        raise EconomicDataError(
            "TLS certificate verification failed "
            f"while fetching {url}. "
            "For development only, set "
            "JUMUIYA_ECONOMIC_ALLOW_INSECURE_TLS=true."
        ) from exc

    except requests.RequestException as exc:

        raise EconomicDataError(
            f"Unable to fetch {url}: {exc}"
        ) from exc


# =========================================================
# HTML NORMALIZATION
# =========================================================

def html_to_text(
    html: str,
) -> str:
    """
    Convert HTML into compact searchable text.
    """

    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    html = re.sub(
        r"&nbsp;",
        " ",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"&amp;",
        "&",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"\s+",
        " ",
        html,
    )

    return html.strip()


# =========================================================
# GENERIC NUMBER EXTRACTION
# =========================================================

def extract_after(
    text: str,
    label: str,
) -> float | None:
    """
    Extract a numeric value after a label.
    """

    pattern = re.compile(
        rf"{re.escape(label)}"
        rf"\s*[:|]?\s*"
        rf"([0-9]+(?:\.[0-9]+)?)"
        rf"\s*%?",
        flags=re.I,
    )

    match = pattern.search(
        text
    )

    if not match:

        return None

    return safe_float(
        match.group(1)
    )


# =========================================================
# CBK MONETARY POLICY
# =========================================================

def fetch_cbk_key_rates() -> dict[str, Any]:
    """
    Read the currently published CBK key rates.
    """

    html = fetch_url(
        CBK_MONETARY_POLICY_URL
    )

    text = html_to_text(
        html
    )

    labels = {
        "central_bank_rate_percent": (
            "Central Bank Rate"
        ),
        "kesonia_percent": (
            "KESONIA"
        ),
        "cbk_discount_window_percent": (
            "CBK Discount Window"
        ),
        "91_day_tbill_percent": (
            "91-Day T-Bill"
        ),
        "repo_percent": (
            "REPO"
        ),
        "inflation_rate_percent": (
            "Inflation Rate"
        ),
        "lending_rate_percent": (
            "Lending Rate"
        ),
        "savings_rate_percent": (
            "Savings Rate"
        ),
        "deposit_rate_percent": (
            "Deposit Rate"
        ),
    }

    result: dict[str, Any] = {}

    for key, label in labels.items():

        value = extract_after(
            text,
            label,
        )

        if value is not None:

            result[key] = value

    result.update(
        {
            "source": "CBK",
            "source_url": CBK_MONETARY_POLICY_URL,
            "fetched_at": now_iso(),
        }
    )

    return result


# =========================================================
# CBK FOREX
# =========================================================

def fetch_cbk_forex() -> dict[str, Any]:
    """
    Fetch currently published KES foreign exchange rates.
    """

    html = fetch_url(
        CBK_FOREX_URL
    )

    text = html_to_text(
        html
    )

    currencies = {
        "USD": r"US DOLLAR",
        "GBP": r"STG POUND",
        "EUR": r"EURO",
        "ZAR": r"SA RAND",
        "AED": r"AE DIRHAM",
        "CAD": r"CAN \$",
        "CHF": r"S FRANC",
    }

    result: dict[str, Any] = {}

    for code, label in currencies.items():

        pattern = re.compile(
            rf"{label}"
            rf"\s+"
            rf"([0-9]+(?:\.[0-9]+)?)"
            rf"\s+"
            rf"([0-9]+(?:\.[0-9]+)?)"
            rf"\s+"
            rf"([0-9]+(?:\.[0-9]+)?)",
            flags=re.I,
        )

        match = pattern.search(
            text
        )

        if match:

            result[code] = {
                "mean": safe_float(
                    match.group(1)
                ),
                "buy": safe_float(
                    match.group(2)
                ),
                "sell": safe_float(
                    match.group(3)
                ),
            }

    result.update(
        {
            "source": "CBK",
            "source_url": CBK_FOREX_URL,
            "fetched_at": now_iso(),
        }
    )

    return result


# =========================================================
# CBK INFLATION
# =========================================================

def fetch_cbk_inflation() -> dict[str, Any]:
    """
    Fetch the latest inflation figure from CBK.
    """

    html = fetch_url(
        CBK_INFLATION_URL
    )

    text = html_to_text(
        html
    )

    result: dict[str, Any] = {
        "source": "CBK",
        "source_url": CBK_INFLATION_URL,
        "fetched_at": now_iso(),
    }

    months = (
        "January|February|March|April|"
        "May|June|July|August|September|"
        "October|November|December"
    )

    pattern = re.compile(
        rf"2026\s+"
        rf"({months})\s+"
        rf"([0-9]+(?:\.[0-9]+)?)"
        rf"\s+"
        rf"([0-9]+(?:\.[0-9]+)?)",
        flags=re.I,
    )

    match = pattern.search(
        text
    )

    if match:

        result.update(
            {
                "year": 2026,
                "month": match.group(1),
                "annual_average_percent": (
                    safe_float(
                        match.group(2)
                    )
                ),
                "twelve_month_percent": (
                    safe_float(
                        match.group(3)
                    )
                ),
            }
        )

    return result


# =========================================================
# KNBS ECONOMIC SURVEY
# =========================================================

def fetch_knbs_economic_survey() -> dict[str, Any]:
    """
    Fetch the latest KNBS Economic Survey landing page.
    """

    html = fetch_url(
        KNBS_ECONOMIC_SURVEY_URL
    )

    text = html_to_text(
        html
    )

    result: dict[str, Any] = {
        "source": "KNBS",
        "source_url": KNBS_ECONOMIC_SURVEY_URL,
        "publication": "2026 Economic Survey",
        "reference_year": 2025,
        "fetched_at": now_iso(),
    }

    patterns = {
        "real_gdp_growth_percent": (
            r"real Gross Domestic Product "
            r"\(GDP\) grew by\s+"
            r"([0-9]+(?:\.[0-9]+)?)"
        ),
        "agriculture_growth_percent": (
            r"Agriculture,\s*Forestry and Fishing"
            r"[^.]*expanded by\s+"
            r"([0-9]+(?:\.[0-9]+)?)"
        ),
        "construction_growth_percent": (
            r"Construction activities"
            r"[^.]*grow(?:n)? by\s+"
            r"([0-9]+(?:\.[0-9]+)?)"
        ),
        "mining_growth_percent": (
            r"Mining and Quarrying"
            r"[^.]*?"
            r"([0-9]+(?:\.[0-9]+)?)"
            r"(?:\s+per cent|\%)"
        ),
        "accommodation_food_services_growth_percent": (
            r"Accommodation\s*&\s*Food Service"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "public_administration_growth_percent": (
            r"Public Administration"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "financial_insurance_growth_percent": (
            r"Financial\s*&\s*Insurance"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "information_communication_growth_percent": (
            r"Information and Communication"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "transport_storage_growth_percent": (
            r"Transportation and Storage"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "wholesale_retail_growth_percent": (
            r"Wholesale and Retail Trade"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
    }

    for key, pattern in patterns.items():

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if match:

            result[key] = safe_float(
                match.group(1)
            )

    return result


# =========================================================
# KNBS CPI
# =========================================================

def fetch_knbs_cpi() -> dict[str, Any]:
    """
    Fetch latest KNBS CPI publication.
    """

    html = fetch_url(
        KNBS_CPI_URL
    )

    text = html_to_text(
        html
    )

    result: dict[str, Any] = {
        "source": "KNBS",
        "source_url": KNBS_CPI_URL,
        "reference_year": 2026,
        "reference_month": "August",
        "fetched_at": now_iso(),
    }

    headline = re.search(
        r"Annual consumer price inflation was\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s+"
        r"per cent in August 2026",
        text,
        flags=re.I,
    )

    if headline:

        result[
            "headline_inflation_percent"
        ] = safe_float(
            headline.group(1)
        )

    division_patterns = {
        "food_non_alcoholic_beverages_percent": (
            r"Food and Non-Alcoholic Beverages"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "transport_percent": (
            r"Transport"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
        "housing_water_electricity_fuels_percent": (
            r"Housing,\s*Water,\s*Electricity,"
            r"\s*Gas and other fuels"
            r"\s*\("
            r"([0-9]+(?:\.[0-9]+)?)"
            r"%\)"
        ),
    }

    for key, pattern in division_patterns.items():

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if match:

            result[key] = safe_float(
                match.group(1)
            )

    return result


# =========================================================
# CACHE
# =========================================================

def _load_cache() -> dict[str, Any]:
    """
    Read the previous successful snapshot.
    """

    if not CACHE_FILE.exists():

        return {}

    try:

        return json.loads(
            CACHE_FILE.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
    ):

        LOGGER.warning(
            "Economic cache is unreadable."
        )

        return {}


def _write_cache(
    data: dict[str, Any],
) -> None:
    """
    Atomically replace the cache file.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = json.dumps(
        data,
        indent=2,
        ensure_ascii=False,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="economic_",
        suffix=".json",
        dir=DATA_DIR,
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:

            handle.write(
                payload
            )

        os.replace(
            temp_name,
            CACHE_FILE,
        )

    finally:

        try:
            os.remove(
                temp_name
            )
        except FileNotFoundError:
            pass


# =========================================================
# REFRESH
# =========================================================

def refresh_economic_indicators() -> dict[str, Any]:
    """
    Fetch all configured sources.

    A partial refresh is still useful:

    successful sources are cached while failed sources
    are reported explicitly.
    """

    started_at = now_iso()

    collectors = {
        "cbk_key_rates": fetch_cbk_key_rates,
        "cbk_forex": fetch_cbk_forex,
        "cbk_inflation": fetch_cbk_inflation,
        "knbs_economic_survey": fetch_knbs_economic_survey,
        "knbs_cpi": fetch_knbs_cpi,
    }

    sources: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for name, collector in collectors.items():

        try:

            sources[name] = collector()

            LOGGER.info(
                "Economic source succeeded: %s",
                name,
            )

        except Exception as exc:

            LOGGER.exception(
                "Economic source failed: %s",
                name,
            )

            errors[name] = str(
                exc
            )

    previous = _load_cache()

    # -----------------------------------------------------
    # NO SOURCE SUCCEEDED
    # -----------------------------------------------------

    if not sources:

        if previous:

            stale_cache = dict(
                previous
            )

            stale_cache[
                "source_status"
            ] = "stale"

            stale_cache[
                "refresh"
            ] = {
                "status": "stale",
                "attempted_at": started_at,
                "successful_sources": [],
                "failed_sources": list(
                    errors.keys()
                ),
                "errors": errors,
            }

            _write_cache(
                stale_cache
            )

            return stale_cache

        failed = {
            "dataset": (
                "kenya_economic_indicators"
            ),
            "country": "Kenya",
            "country_code": "KE",
            "version": "2.0.0",
            "source_status": "unavailable",
            "updated_at": started_at,
            "refresh": {
                "status": "failed",
                "attempted_at": started_at,
                "successful_sources": [],
                "failed_sources": list(
                    errors.keys()
                ),
                "errors": errors,
            },
            "sources": {},
        }

        _write_cache(
            failed
        )

        return failed

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if errors:

        status = "partial"

    else:

        status = "live"

    # -----------------------------------------------------
    # DATASET
    # -----------------------------------------------------

    data = {
        "dataset": (
            "kenya_economic_indicators"
        ),
        "country": "Kenya",
        "country_code": "KE",
        "version": "2.0.0",
        "source_status": status,
        "updated_at": started_at,
        "refresh": {
            "status": status,
            "attempted_at": started_at,
            "successful_sources": list(
                sources.keys()
            ),
            "failed_sources": list(
                errors.keys()
            ),
            "errors": errors,
        },
        "sources": sources,
    }

    _write_cache(
        data
    )

    return data


# =========================================================
# READ
# =========================================================

def get_economic_indicators(
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Return economic data.

    refresh=True:
        fetch live sources first.

    refresh=False:
        return cache when available;
        fetch live data when no cache exists.
    """

    if refresh:

        return refresh_economic_indicators()

    cached = _load_cache()

    if cached:

        return cached

    return refresh_economic_indicators()


# =========================================================
# HEALTH
# =========================================================

def economic_data_health() -> dict[str, Any]:
    """
    Return health information without exposing secrets.
    """

    cache = _load_cache()

    sources = cache.get(
        "sources",
        {},
    )

    if not isinstance(
        sources,
        dict,
    ):

        sources = {}

    return {
        "service": (
            "jumuiya_biashara_economic_data"
        ),
        "status": (
            cache.get(
                "source_status",
                "not_initialized",
            )
        ),
        "cache_exists": (
            CACHE_FILE.exists()
        ),
        "cache_file": str(
            CACHE_FILE
        ),
        "last_updated": (
            cache.get(
                "updated_at"
            )
        ),
        "development_insecure_tls": (
            _insecure_tls_enabled()
        ),
        "sources": {
            name: (
                name in sources
            )
            for name in (
                "cbk_key_rates",
                "cbk_forex",
                "cbk_inflation",
                "knbs_economic_survey",
                "knbs_cpi",
            )
        },
    }


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    result = (
        refresh_economic_indicators()
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )