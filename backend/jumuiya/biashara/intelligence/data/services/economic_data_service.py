"""
Live Kenya economic data service for Jumuiya / Biashara Intelligence.

Sources:
- Central Bank of Kenya (CBK): key rates, daily FX, inflation.
- Kenya National Bureau of Statistics (KNBS): latest Economic Survey and CPI release.

This module keeps a local JSON cache so the application remains available when
an upstream source is temporarily unavailable. The cache is NOT the source of
truth; it is only the latest successfully fetched snapshot.
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


LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "economic_indicators.json"

REQUEST_TIMEOUT = int(os.getenv("JUMUIYA_ECONOMIC_TIMEOUT", "20"))

CBK_KEY_RATES_URL = "https://www.centralbank.go.ke/statistics/key-rates/"
CBK_FOREX_URL = "https://www.centralbank.go.ke/rates/forex-exchange-rates/"
CBK_INFLATION_URL = "https://www.centralbank.go.ke/inflation-rates/"
KNBS_ECONOMIC_SURVEY_URL = "https://www.knbs.or.ke/reports/2026-economic-survey/"
KNBS_CPI_URL = "https://www.knbs.or.ke/reports/consumer-price-indices-and-inflation-rates-august-2026/"

USER_AGENT = (
    "Mozilla/5.0 (compatible; RevelaCode-Jumuiya-EconomicBot/1.0; "
    "+https://revelacode-frontend.onrender.com/)"
)


class EconomicDataError(RuntimeError):
    """Raised when live economic data cannot be collected."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _fetch(url: str) -> str:
    if requests is None:
        raise EconomicDataError("The requests package is not installed")

    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _text(html: str) -> str:
    """Convert HTML to compact plain text without requiring BeautifulSoup."""
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html, flags=re.I)
    html = re.sub(r"&amp;", "&", html, flags=re.I)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def _extract_number_after(text: str, label: str) -> float | None:
    pattern = re.compile(
        rf"{re.escape(label)}\s*[:|]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        flags=re.I,
    )
    match = pattern.search(text)
    return _safe_float(match.group(1)) if match else None


def fetch_cbk_key_rates() -> dict[str, Any]:
    html = _fetch(CBK_KEY_RATES_URL)
    text = _text(html)

    indicators: dict[str, Any] = {}

    labels = {
        "central_bank_rate_percent": "Central Bank Rate",
        "kesonia_percent": "KESONIA",
        "cbk_discount_window_percent": "CBK Discount Window",
        "91_day_tbill_percent": "91-Day T-Bill",
        "repo_percent": "REPO",
        "inflation_rate_percent": "Inflation Rate",
        "lending_rate_percent": "Lending Rate",
        "savings_rate_percent": "Savings Rate",
        "deposit_rate_percent": "Deposit Rate",
    }

    for key, label in labels.items():
        value = _extract_number_after(text, label)
        if value is not None:
            indicators[key] = value

    # Keep a useful raw reference in case CBK changes page formatting.
    indicators["source_url"] = CBK_KEY_RATES_URL
    indicators["fetched_at"] = _now_iso()
    return indicators


def fetch_cbk_forex() -> dict[str, Any]:
    html = _fetch(CBK_FOREX_URL)
    text = _text(html)

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
            rf"{label}\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
            flags=re.I,
        )
        match = pattern.search(text)
        if match:
            result[code] = {
                "mean": _safe_float(match.group(1)),
                "buy": _safe_float(match.group(2)),
                "sell": _safe_float(match.group(3)),
            }

    result["source_url"] = CBK_FOREX_URL
    result["fetched_at"] = _now_iso()
    return result


def fetch_cbk_inflation() -> dict[str, Any]:
    html = _fetch(CBK_INFLATION_URL)
    text = _text(html)

    # Prefer the first 2026 month row, which currently represents the newest
    # published entry on the CBK inflation page.
    match = re.search(
        r"2026\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
        text,
        flags=re.I,
    )

    result: dict[str, Any] = {"source_url": CBK_INFLATION_URL, "fetched_at": _now_iso()}
    if match:
        result.update(
            {
                "year": 2026,
                "month": match.group(1),
                "annual_average_percent": _safe_float(match.group(2)),
                "twelve_month_percent": _safe_float(match.group(3)),
            }
        )
    return result


def fetch_knbs_economic_survey() -> dict[str, Any]:
    html = _fetch(KNBS_ECONOMIC_SURVEY_URL)
    text = _text(html)

    result: dict[str, Any] = {
        "source_url": KNBS_ECONOMIC_SURVEY_URL,
        "fetched_at": _now_iso(),
        "reference_year": 2025,
        "publication": "2026 Economic Survey",
    }

    patterns = {
        "real_gdp_growth_percent": r"real Gross Domestic Product \(GDP\) grew by\s+([0-9]+(?:\.[0-9]+)?)",
        "nominal_gdp_ksh_billion": r"Nominal GDP increased from KSh\s*[0-9,\.]+\s*billion in 2024 to KSh\s*([0-9,\.]+)\s*billion in 2025",
        "gdp_per_capita_ksh": r"GDP per capita increased to KSh\s*([0-9,]+)",
        "agriculture_growth_percent": r"Agriculture, Forestry and Fishing[^.]*expanded by\s+([0-9]+(?:\.[0-9]+)?)",
        "construction_growth_percent": r"Construction activities[^.]*grow(?:n)? by\s+([0-9]+(?:\.[0-9]+)?)",
        "mining_growth_percent": r"Mining and Quarrying[^.]*to\s+([0-9]+(?:\.[0-9]+)?)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.I)
        if match:
            result[key] = _safe_float(match.group(1))

    return result


def fetch_knbs_cpi() -> dict[str, Any]:
    html = _fetch(KNBS_CPI_URL)
    text = _text(html)

    result: dict[str, Any] = {
        "source_url": KNBS_CPI_URL,
        "fetched_at": _now_iso(),
        "reference_year": 2026,
        "reference_month": "August",
    }

    match = re.search(
        r"Annual consumer price inflation was\s+([0-9]+(?:\.[0-9]+)?)\s+per cent in August 2026",
        text,
        flags=re.I,
    )
    if match:
        result["headline_inflation_percent"] = _safe_float(match.group(1))

    for key, label in {
        "food_non_alcoholic_beverages_percent": "Food and Non-Alcoholic Beverages",
        "transport_percent": "Transport",
        "housing_water_electricity_fuels_percent": "Housing, Water, Electricity, Gas and other fuels",
    }.items():
        match = re.search(
            rf"{re.escape(label)}\s*\(([0-9]+(?:\.[0-9]+)?)%\)",
            text,
            flags=re.I,
        )
        if match:
            result[key] = _safe_float(match.group(1))

    return result


def _load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False)

    fd, temp_name = tempfile.mkstemp(prefix="economic_", suffix=".json", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temp_name, CACHE_FILE)
    finally:
        try:
            os.remove(temp_name)
        except FileNotFoundError:
            pass


def refresh_economic_indicators() -> dict[str, Any]:
    """Fetch the live sources and atomically update the local cache."""
    fetched_at = _now_iso()
    source_results: dict[str, Any] = {}
    source_errors: dict[str, str] = {}

    collectors = {
        "cbk_key_rates": fetch_cbk_key_rates,
        "cbk_forex": fetch_cbk_forex,
        "cbk_inflation": fetch_cbk_inflation,
        "knbs_economic_survey": fetch_knbs_economic_survey,
        "knbs_cpi": fetch_knbs_cpi,
    }

    for name, collector in collectors.items():
        try:
            source_results[name] = collector()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Economic source failed: %s", name)
            source_errors[name] = str(exc)

    previous = _load_cache()
    successful = bool(source_results)

    if not successful and previous:
        previous.setdefault("refresh", {})
        previous["refresh"].update(
            {
                "status": "stale",
                "attempted_at": fetched_at,
                "errors": source_errors,
            }
        )
        _write_cache(previous)
        return previous

    data = {
        "dataset": "kenya_economic_indicators",
        "country": "Kenya",
        "country_code": "KE",
        "version": "2.0.0",
        "source_status": "live" if not source_errors else "partial",
        "updated_at": fetched_at,
        "refresh": {
            "status": "success" if not source_errors else "partial",
            "attempted_at": fetched_at,
            "errors": source_errors,
        },
        "sources": source_results,
        "business_intelligence": {
            "note": "Use source reference periods when comparing indicators; live daily indicators and annual indicators update on different schedules."
        },
    }

    _write_cache(data)
    return data


def get_economic_indicators(refresh: bool = False) -> dict[str, Any]:
    """Return live data after refresh, or the latest local snapshot."""
    if refresh:
        return refresh_economic_indicators()

    cache = _load_cache()
    if cache:
        return cache

    return refresh_economic_indicators()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = refresh_economic_indicators()
    print(json.dumps(result, indent=2, ensure_ascii=False))
