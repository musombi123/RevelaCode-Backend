# backend/jumuiya/biashara/intelligence/services/market_data_service.py

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None


# =========================================================
# LOGGING
# =========================================================

LOGGER = logging.getLogger(__name__)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

CACHE_FILE = DATA_DIR / "market_signals.json"


# =========================================================
# OFFICIAL SOURCES
# =========================================================

KAMIS_URL = os.getenv(
    "JUMUIYA_KAMIS_URL",
    "https://kamis.kilimo.go.ke/site/market",
)

KAMIS_SEARCH_URL = os.getenv(
    "JUMUIYA_KAMIS_SEARCH_URL",
    "https://kamis.kilimo.go.ke/site/market_search",
)

EPRA_URL = os.getenv(
    "JUMUIYA_EPRA_URL",
    "https://www.epra.go.ke/EPRA%20Pump%20Prices",
)

KNBS_CPI_URL = os.getenv(
    "JUMUIYA_KNBS_CPI_URL",
    "https://www.knbs.or.ke/reports/consumer-price-indices-and-inflation-rates-august-2026/",
)


# =========================================================
# HTTP
# =========================================================

DEFAULT_TIMEOUT = int(
    os.getenv(
        "JUMUIYA_MARKET_HTTP_TIMEOUT",
        "30",
    )
)

USER_AGENT = os.getenv(
    "JUMUIYA_MARKET_USER_AGENT",
    (
        "RevelaCode-Jumuiya/1.0 "
        "(Biashara Market Intelligence)"
    ),
)


# =========================================================
# STATUS
# =========================================================

LIVE = "live"
PARTIAL = "partial"
STALE = "stale"
UNAVAILABLE = "unavailable"


# =========================================================
# FRESHNESS
# =========================================================

# KAMIS observations are market observations and should not
# silently be treated as current if their observation date is
# too old.
KAMIS_MAX_AGE_DAYS = int(
    os.getenv(
        "JUMUIYA_KAMIS_MAX_AGE_DAYS",
        "7",
    )
)

# EPRA prices are published by pricing period rather than
# transaction-by-transaction.
EPRA_MAX_AGE_DAYS = int(
    os.getenv(
        "JUMUIYA_EPRA_MAX_AGE_DAYS",
        "45",
    )
)

# KNBS CPI is a periodic statistical release.
KNBS_MAX_AGE_DAYS = int(
    os.getenv(
        "JUMUIYA_KNBS_MAX_AGE_DAYS",
        "45",
    )
)


# =========================================================
# TLS
# =========================================================

def _verify_setting():
    """
    Return the normal TLS verification configuration.
    """

    if certifi is not None:
        return certifi.where()

    return True


def _insecure_tls_enabled() -> bool:
    """
    Development-only escape hatch for broken local CA chains.

    Never enable this in production.
    """

    return (
        os.getenv(
            "JUMUIYA_MARKET_ALLOW_INSECURE_TLS",
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
# HTTP FETCH
# =========================================================

def fetch_url(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """
    Fetch a remote HTML page.

    TLS verification remains enabled by default.
    """

    if not url:
        raise ValueError(
            "A source URL is required."
        )

    insecure_tls = _insecure_tls_enabled()

    verify = (
        False
        if insecure_tls
        else _verify_setting()
    )

    LOGGER.info(
        "Fetching market source: %s | TLS verification=%s",
        url,
        verify,
    )

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Cache-Control": "no-cache",
        },
        verify=verify,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


# =========================================================
# HTML TABLE PARSER
# =========================================================

class TableParser(HTMLParser):
    """
    Small dependency-free HTML table parser.

    Produces:

        [
            ["Header 1", "Header 2"],
            ["Value 1", "Value 2"],
        ]
    """

    def __init__(self):
        super().__init__()

        self.tables: list[list[list[str]]] = []

        self._inside_table = False
        self._inside_row = False
        self._inside_cell = False

        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs,
    ):
        tag = tag.lower()

        if tag == "table":
            self._inside_table = True
            self._current_table = []

        elif (
            tag == "tr"
            and self._inside_table
        ):
            self._inside_row = True
            self._current_row = []

        elif (
            tag in {"td", "th"}
            and self._inside_row
        ):
            self._inside_cell = True
            self._current_cell = []

    def handle_data(
        self,
        data: str,
    ):
        if self._inside_cell:
            self._current_cell.append(
                data
            )

    def handle_endtag(
        self,
        tag: str,
    ):
        tag = tag.lower()

        if (
            tag in {"td", "th"}
            and self._inside_cell
        ):
            value = "".join(
                self._current_cell
            )

            value = re.sub(
                r"\s+",
                " ",
                value,
            ).strip()

            self._current_row.append(
                value
            )

            self._inside_cell = False

        elif (
            tag == "tr"
            and self._inside_row
        ):
            if self._current_row:
                self._current_table.append(
                    self._current_row
                )

            self._inside_row = False

        elif (
            tag == "table"
            and self._inside_table
        ):
            if self._current_table:
                self.tables.append(
                    self._current_table
                )

            self._current_table = []
            self._inside_table = False


def parse_tables(
    html: str,
) -> list[list[list[str]]]:
    parser = TableParser()

    parser.feed(
        html
    )

    return parser.tables


# =========================================================
# TEXT HELPERS
# =========================================================

def normalize_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def normalize_key(
    value: Any,
) -> str:
    return normalize_text(
        value
    ).lower()


def first_nonempty(
    values: list[Any],
    default: str = "",
) -> str:
    for value in values:
        normalized = normalize_text(
            value
        )

        if normalized:
            return normalized

    return default


def parse_float(
    value: Any,
) -> float | None:
    """
    Extract a numeric value from strings such as:

        65.00/Kg
        KES 210.87
        12,500.00
    """

    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    text = text.replace(
        ",",
        "",
    )

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text,
    )

    if not match:
        return None

    try:
        return float(
            match.group(
                0
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def parse_date(
    value: Any,
) -> str | None:
    """
    Normalize common date formats to YYYY-MM-DD.
    """

    text = normalize_text(
        value
    )

    if not text:
        return None

    match = re.search(
        r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
        text,
    )

    if match:
        year, month, day = (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        )

        return (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )

    return None


def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


def iso_now() -> str:
    return now_utc().isoformat()


def age_days(
    date_text: str | None,
) -> float | None:
    if not date_text:
        return None

    try:
        parsed = datetime.strptime(
            date_text,
            "%Y-%m-%d",
        ).replace(
            tzinfo=timezone.utc
        )

        return max(
            0.0,
            (
                now_utc()
                - parsed
            ).total_seconds()
            / 86400.0,
        )

    except ValueError:
        return None


def freshness_status(
    observed_date: str | None,
    max_age_days: int,
) -> str:
    age = age_days(
        observed_date
    )

    if age is None:
        return "unknown"

    if age <= max_age_days:
        return "fresh"

    return "stale"


# =========================================================
# KAMIS
# =========================================================

def _find_table(
    tables: list[list[list[str]]],
    required_headers: set[str],
) -> list[list[str]] | None:
    """
    Find a table whose header row contains all required fields.
    """

    for table in tables:

        if not table:
            continue

        headers = {
            normalize_key(
                header
            )
            for header in table[0]
        }

        if required_headers.issubset(
            headers
        ):
            return table

    return None


def _row_to_dict(
    headers: list[str],
    row: list[str],
) -> dict[str, str]:
    result = {}

    for index, header in enumerate(
        headers
    ):

        if index >= len(row):
            result[
                normalize_key(
                    header
                )
            ] = ""

            continue

        result[
            normalize_key(
                header
            )
        ] = normalize_text(
            row[index]
        )

    return result


def parse_kamis(
    html: str,
) -> list[dict]:
    """
    Parse KAMIS market-price observations.

    KAMIS publishes fields including:

        Commodity
        Classification
        Market
        Wholesale
        Retail
        Supply Volume
        County
        Date
    """

    tables = parse_tables(
        html
    )

    required_headers = {
        "market",
        "commodity",
        "wholesale",
        "retail",
        "supply volume",
        "county",
        "date",
    }

    table = _find_table(
        tables,
        required_headers,
    )

    if table is None:
        return []

    headers = table[0]

    observations = []

    for row in table[1:]:

        if not row:
            continue

        record = _row_to_dict(
            headers,
            row,
        )

        commodity = first_nonempty(
            [
                record.get(
                    "commodity"
                ),
            ]
        )

        market = first_nonempty(
            [
                record.get(
                    "market"
                ),
            ]
        )

        county = first_nonempty(
            [
                record.get(
                    "county"
                ),
            ]
        )

        if not commodity or not market:
            continue

        observation_date = parse_date(
            record.get(
                "date"
            )
        )

        wholesale = parse_float(
            record.get(
                "wholesale"
            )
        )

        retail = parse_float(
            record.get(
                "retail"
            )
        )

        supply_volume = parse_float(
            record.get(
                "supply volume"
            )
        )

        observations.append(
            {
                "source": "kamis",
                "commodity": commodity,
                "classification": first_nonempty(
                    [
                        record.get(
                            "classification"
                        ),
                    ]
                ),
                "grade": first_nonempty(
                    [
                        record.get(
                            "grade"
                        ),
                    ]
                ),
                "sex": first_nonempty(
                    [
                        record.get(
                            "sex"
                        ),
                    ]
                ),
                "market": market,
                "county": county,
                "wholesale_price": wholesale,
                "retail_price": retail,
                "supply_volume": supply_volume,
                "unit": "KES",
                "observed_date": observation_date,
            }
        )

    return observations


def fetch_kamis(
    url: str | None = None,
) -> dict:
    """
    Fetch live KAMIS market observations.
    """

    source_url = (
        url or KAMIS_URL
    )

    html = fetch_url(
        source_url
    )

    observations = parse_kamis(
        html
    )

    if not observations:

        raise ValueError(
            "KAMIS response contained no valid market observations."
        )

    observed_dates = [
        item.get(
            "observed_date"
        )
        for item in observations
        if item.get(
            "observed_date"
        )
    ]

    latest_date = max(
        observed_dates
    ) if observed_dates else None

    freshness = freshness_status(
        latest_date,
        KAMIS_MAX_AGE_DAYS,
    )

    return {
        "source": "kamis",
        "status": (
            LIVE
            if freshness == "fresh"
            else STALE
        ),
        "source_url": source_url,
        "fetched_at": iso_now(),
        "latest_observation_date": latest_date,
        "freshness": freshness,
        "records": len(
            observations
        ),
        "data": observations,
    }


# =========================================================
# EPRA
# =========================================================

def _extract_epra_prices(
    html: str,
) -> list[dict]:
    """
    Parse the visible EPRA fuel-price index.

    Example labels:

        Mombasa PMS
        Nairobi PMS
        Mombasa AGO
        Nairobi AGO
        Mombasa IK
    """

    text = re.sub(
        r"\s+",
        " ",
        re.sub(
            r"<[^>]+>",
            " ",
            html,
        ),
    ).strip()

    records = []

    locations = [
        "Mombasa",
        "Nairobi",
        "Nakuru",
        "Eldoret",
        "Kisumu",
    ]

    products = [
        "PMS",
        "AGO",
        "IK",
    ]

    for location in locations:

        for product in products:

            pattern = (
                rf"{re.escape(location)}\s+"
                rf"{re.escape(product)}\s+"
                rf"([0-9]+(?:\.[0-9]+)?)"
            )

            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            price = parse_float(
                match.group(
                    1
                )
            )

            if price is None:
                continue

            records.append(
                {
                    "source": "epra",
                    "location": location,
                    "product": product,
                    "price": price,
                    "unit": "KES/litre",
                }
            )

    return records


def _extract_epra_period(
    html: str,
) -> str | None:
    """
    Try to recover the current EPRA price-period end date.

    Expected text may contain:

        15th August 2026 - 14th September 2026
    """

    text = re.sub(
        r"\s+",
        " ",
        re.sub(
            r"<[^>]+>",
            " ",
            html,
        ),
    ).strip()

    pattern = (
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?\s+"
        r"([A-Za-z]+)\s+"
        r"(\d{4})\s*"
        r"(?:-|–|to)\s*"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?\s+"
        r"([A-Za-z]+)\s+"
        r"(\d{4})"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    end_day = int(
        match.group(4)
    )

    end_month = match.group(5)

    end_year = int(
        match.group(6)
    )

    for month_format in (
        "%d %B %Y",
        "%d %b %Y",
    ):

        try:
            parsed = datetime.strptime(
                (
                    f"{end_day} "
                    f"{end_month} "
                    f"{end_year}"
                ),
                month_format,
            )

            return parsed.strftime(
                "%Y-%m-%d"
            )

        except ValueError:
            continue

    return None


def fetch_epra(
    url: str | None = None,
) -> dict:
    """
    Fetch live EPRA fuel-price index.
    """

    source_url = (
        url or EPRA_URL
    )

    html = fetch_url(
        source_url
    )

    records = _extract_epra_prices(
        html
    )

    if not records:

        raise ValueError(
            "EPRA response contained no recognized fuel prices."
        )

    period_end = _extract_epra_period(
        html
    )

    freshness = freshness_status(
        period_end,
        EPRA_MAX_AGE_DAYS,
    )

    return {
        "source": "epra",
        "status": (
            LIVE
            if freshness in {
                "fresh",
                "unknown",
            }
            else STALE
        ),
        "source_url": source_url,
        "fetched_at": iso_now(),
        "latest_period_end": period_end,
        "freshness": freshness,
        "records": len(
            records
        ),
        "data": records,
    }


# =========================================================
# KNBS
# =========================================================

def _extract_percentage(
    text: str,
    label_patterns: list[str],
) -> float | None:
    for label_pattern in label_patterns:

        pattern = (
            label_pattern
            + r".{0,180}?"
            + r"(\d+(?:\.\d+)?)"
            + r"\s*%"
        )

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:

            return parse_float(
                match.group(
                    1
                )
            )

    return None


def _extract_knbs_reference_period(
    html: str,
) -> tuple[int | None, str | None]:
    """
    Attempt to recover the reporting month/year
    from the KNBS CPI page.
    """

    text = re.sub(
        r"\s+",
        " ",
        re.sub(
            r"<[^>]+>",
            " ",
            html,
        ),
    ).strip()

    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+"
        r"(20\d{2})",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return (
            None,
            None,
        )

    month = (
        match.group(
            1
        ).capitalize()
    )

    year = int(
        match.group(
            2
        )
    )

    return (
        year,
        month,
    )


def fetch_knbs(
    url: str | None = None,
) -> dict:
    """
    Fetch current KNBS CPI page and extract major
    consumer-price signals.

    KNBS CPI is periodic rather than transaction-level,
    so freshness is based on the publication reference period.
    """

    source_url = (
        url or KNBS_CPI_URL
    )

    html = fetch_url(
        source_url
    )

    clean_text = re.sub(
        r"\s+",
        " ",
        re.sub(
            r"<[^>]+>",
            " ",
            html,
        ),
    ).strip()

    year, month = (
        _extract_knbs_reference_period(
            html
        )
    )

    if year is None or not month:
        raise ValueError(
            "Could not determine KNBS CPI reference period."
        )

    month_number = datetime.strptime(
        month,
        "%B",
    ).month

    reference_date = datetime(
        year,
        month_number,
        1,
        tzinfo=timezone.utc,
    )

    age = (
        now_utc()
        - reference_date
    ).total_seconds() / 86400.0

    if age < 0:
        freshness = "fresh"
    elif age <= KNBS_MAX_AGE_DAYS:
        freshness = "fresh"
    else:
        freshness = "stale"

    headline = (
        _extract_percentage(
            clean_text,
            [
                r"Annual consumer price inflation was",
                r"annual consumer price inflation",
                r"headline inflation",
            ],
        )
    )

    food = (
        _extract_percentage(
            clean_text,
            [
                r"Food and Non-Alcoholic Beverages",
                r"Food and Non-Alcoholic",
            ],
        )
    )

    transport = (
        _extract_percentage(
            clean_text,
            [
                r"Transport",
            ],
        )
    )

    housing = (
        _extract_percentage(
            clean_text,
            [
                r"Housing, Water, Electricity, Gas and Other Fuels",
                r"Housing, Water, Electricity, Gas and other fuels",
                r"Housing, Water, Electricity",
            ],
        )
    )

    if headline is None:
        raise ValueError(
            "KNBS CPI headline inflation was not found."
        )

    data = {
        "reference_year": year,
        "reference_month": month,
        "headline_inflation_percent": headline,
        "food_non_alcoholic_beverages_percent": food,
        "transport_percent": transport,
        "housing_water_electricity_gas_fuels_percent": housing,
    }

    return {
        "source": "knbs_cpi",
        "status": (
            LIVE
            if freshness == "fresh"
            else STALE
        ),
        "source_url": source_url,
        "fetched_at": iso_now(),
        "reference_year": year,
        "reference_month": month,
        "reference_date": (
            f"{year:04d}-"
            f"{month_number:02d}-01"
        ),
        "freshness": freshness,
        "records": 1,
        "data": data,
    }


# =========================================================
# MARKET SIGNAL CALCULATIONS
# =========================================================

def _group_kamis_by_commodity(
    observations: list[dict],
) -> list[dict]:
    groups: dict[str, list[dict]] = {}

    for observation in observations:

        commodity = normalize_key(
            observation.get(
                "commodity"
            )
        )

        if not commodity:
            continue

        groups.setdefault(
            commodity,
            [],
        ).append(
            observation
        )

    results = []

    for commodity_key, items in groups.items():

        retail_prices = [
            item.get(
                "retail_price"
            )
            for item in items
            if isinstance(
                item.get(
                    "retail_price"
                ),
                (
                    int,
                    float,
                ),
            )
        ]

        wholesale_prices = [
            item.get(
                "wholesale_price"
            )
            for item in items
            if isinstance(
                item.get(
                    "wholesale_price"
                ),
                (
                    int,
                    float,
                ),
            )
        ]

        supplies = [
            item.get(
                "supply_volume"
            )
            for item in items
            if isinstance(
                item.get(
                    "supply_volume"
                ),
                (
                    int,
                    float,
                ),
            )
        ]

        latest_date = max(
            [
                item.get(
                    "observed_date"
                )
                for item in items
                if item.get(
                    "observed_date"
                )
            ],
            default=None,
        )

        average_retail = (
            sum(retail_prices)
            / len(retail_prices)
            if retail_prices
            else None
        )

        average_wholesale = (
            sum(wholesale_prices)
            / len(wholesale_prices)
            if wholesale_prices
            else None
        )

        total_supply = (
            sum(supplies)
            if supplies
            else None
        )

        margin_percent = None

        if (
            average_retail is not None
            and average_wholesale
            and average_wholesale > 0
        ):
            margin_percent = (
                (
                    average_retail
                    - average_wholesale
                )
                / average_wholesale
            ) * 100.0

        results.append(
            {
                "commodity": (
                    items[0].get(
                        "commodity"
                    )
                ),
                "markets_covered": len(
                    {
                        item.get(
                            "market"
                        )
                        for item in items
                        if item.get(
                            "market"
                        )
                    }
                ),
                "counties_covered": len(
                    {
                        item.get(
                            "county"
                        )
                        for item in items
                        if item.get(
                            "county"
                        )
                    }
                ),
                "average_retail_price": (
                    round(
                        average_retail,
                        2,
                    )
                    if average_retail is not None
                    else None
                ),
                "average_wholesale_price": (
                    round(
                        average_wholesale,
                        2,
                    )
                    if average_wholesale is not None
                    else None
                ),
                "total_supply_volume": (
                    round(
                        total_supply,
                        2,
                    )
                    if total_supply is not None
                    else None
                ),
                "wholesale_to_retail_margin_percent": (
                    round(
                        margin_percent,
                        2,
                    )
                    if margin_percent is not None
                    else None
                ),
                "latest_observation_date": latest_date,
                "record_count": len(
                    items
                ),
            }
        )

    return results


def build_market_signals(
    kamis_result: dict | None,
    epra_result: dict | None,
    knbs_result: dict | None,
) -> dict:
    """
    Convert source observations into a compact intelligence
    snapshot while retaining raw source observations.

    No artificial demand score is invented here. Signals are
    derived from observable market prices, supply and macro
    indicators.
    """

    kamis_data = (
        kamis_result.get(
            "data",
            []
        )
        if isinstance(
            kamis_result,
            dict,
        )
        else []
    )

    epra_data = (
        epra_result.get(
            "data",
            []
        )
        if isinstance(
            epra_result,
            dict,
        )
        else []
    )

    knbs_data = (
        knbs_result.get(
            "data",
            {}
        )
        if isinstance(
            knbs_result,
            dict,
        )
        else {}
    )

    commodity_signals = (
        _group_kamis_by_commodity(
            kamis_data
        )
    )

    return {
        "commodity_signals": commodity_signals,
        "fuel_signals": epra_data,
        "macro_price_signals": (
            knbs_data
        ),
    }


# =========================================================
# CACHE
# =========================================================

def _load_cache() -> dict | None:
    """
    Load the last validated cache snapshot.
    """

    if not CACHE_FILE.exists():
        return None

    try:

        with CACHE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict,
        ):
            return None

        return data

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
    ):

        LOGGER.exception(
            "Unable to load market signals cache."
        )

        return None


def _write_cache(
    data: dict,
) -> None:
    """
    Atomically write the market-signals cache.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = CACHE_FILE.with_suffix(
        ".tmp"
    )

    with temp_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write(
            "\n"
        )

    temp_file.replace(
        CACHE_FILE
    )


# =========================================================
# SOURCE STATUS
# =========================================================

def _source_summary(
    result: dict | None,
) -> dict:

    if not isinstance(
        result,
        dict,
    ):
        return {
            "status": UNAVAILABLE,
            "records": 0,
        }

    return {
        "status": result.get(
            "status",
            UNAVAILABLE,
        ),
        "records": int(
            result.get(
                "records",
                0,
            )
            or 0
        ),
        "fetched_at": result.get(
            "fetched_at"
        ),
        "latest_observation_date": result.get(
            "latest_observation_date"
        ),
        "latest_period_end": result.get(
            "latest_period_end"
        ),
        "reference_year": result.get(
            "reference_year"
        ),
        "reference_month": result.get(
            "reference_month"
        ),
        "freshness": result.get(
            "freshness"
        ),
        "source_url": result.get(
            "source_url"
        ),
    }


def _overall_status(
    results: list[dict | None],
) -> str:

    statuses = [
        result.get(
            "status"
        )
        for result in results
        if isinstance(
            result,
            dict,
        )
    ]

    if not statuses:
        return UNAVAILABLE

    live_count = statuses.count(
        LIVE
    )

    partial_count = statuses.count(
        PARTIAL
    )

    stale_count = statuses.count(
        STALE
    )

    if live_count == len(
        statuses
    ):
        return LIVE

    if (
        live_count > 0
        or partial_count > 0
    ):
        return PARTIAL

    if stale_count == len(
        statuses
    ):
        return STALE

    return UNAVAILABLE


# =========================================================
# REFRESH
# =========================================================

def refresh_market_data() -> dict:
    """
    Perform a live market-data refresh.

    All configured official sources are fetched independently.
    A single source failure does not erase the valid data from
    the other sources.

    market_signals.json is written only from the resulting
    validated snapshot.
    """

    started_at = iso_now()

    results: dict[str, dict | None] = {
        "kamis": None,
        "epra": None,
        "knbs_cpi": None,
    }

    errors: dict[str, str] = {}

    # -----------------------------------------------------
    # KAMIS
    # -----------------------------------------------------

    try:

        results["kamis"] = fetch_kamis()

        LOGGER.info(
            "KAMIS market data refreshed: %s records",
            results["kamis"].get(
                "records",
                0,
            ),
        )

    except Exception as exc:

        LOGGER.exception(
            "KAMIS market refresh failed."
        )

        errors["kamis"] = str(
            exc
        )

    # -----------------------------------------------------
    # EPRA
    # -----------------------------------------------------

    try:

        results["epra"] = fetch_epra()

        LOGGER.info(
            "EPRA market data refreshed: %s records",
            results["epra"].get(
                "records",
                0,
            ),
        )

    except Exception as exc:

        LOGGER.exception(
            "EPRA market refresh failed."
        )

        errors["epra"] = str(
            exc
        )

    # -----------------------------------------------------
    # KNBS
    # -----------------------------------------------------

    try:

        results["knbs_cpi"] = fetch_knbs()

        LOGGER.info(
            "KNBS CPI refreshed."
        )

    except Exception as exc:

        LOGGER.exception(
            "KNBS CPI refresh failed."
        )

        errors["knbs_cpi"] = str(
            exc
        )

    # -----------------------------------------------------
    # SIGNALS
    # -----------------------------------------------------

    signal_data = build_market_signals(
        results["kamis"],
        results["epra"],
        results["knbs_cpi"],
    )

    source_results = [
        results["kamis"],
        results["epra"],
        results["knbs_cpi"],
    ]

    status = _overall_status(
        source_results
    )

    completed_at = iso_now()

    payload = {
        "dataset": "kenya_market_signals",
        "country": "Kenya",
        "country_code": "KE",
        "version": "2.0.0",
        "source_status": status,
        "generated_at": completed_at,
        "refresh": {
            "started_at": started_at,
            "completed_at": completed_at,
            "status": status,
            "successful_sources": [
                name
                for name, result in results.items()
                if isinstance(
                    result,
                    dict,
                )
                and result.get(
                    "status"
                )
                in {
                    LIVE,
                    PARTIAL,
                }
            ],
            "failed_sources": list(
                errors.keys()
            ),
            "errors": errors,
        },
        "sources": {
            "kamis": _source_summary(
                results["kamis"]
            ),
            "epra": _source_summary(
                results["epra"]
            ),
            "knbs_cpi": _source_summary(
                results["knbs_cpi"]
            ),
        },
        "signals": signal_data,
        "raw": {
            "kamis": (
                results["kamis"].get(
                    "data",
                    [],
                )
                if results["kamis"]
                else []
            ),
            "epra": (
                results["epra"].get(
                    "data",
                    [],
                )
                if results["epra"]
                else []
            ),
            "knbs_cpi": (
                results["knbs_cpi"].get(
                    "data",
                    {},
                )
                if results["knbs_cpi"]
                else {}
            ),
        },
    }

    # -----------------------------------------------------
    # CACHE VALIDATION
    # -----------------------------------------------------

    valid_payload = (
        status
        in {
            LIVE,
            PARTIAL,
            STALE,
        }
    )

    if valid_payload:

        _write_cache(
            payload
        )

        LOGGER.info(
            "Market signals cache updated: %s",
            CACHE_FILE,
        )

    else:

        LOGGER.error(
            "No usable market source succeeded. "
            "Existing cache was preserved."
        )

    return payload


# =========================================================
# CACHE / LIVE ACCESS
# =========================================================

def get_market_signals(
    refresh: bool = False,
) -> dict:
    """
    Return market signals.

    refresh=True:
        Always performs a live source refresh.

    refresh=False:
        Returns the latest validated cache.

    If no cache exists, performs a live refresh automatically.
    """

    if refresh:
        return refresh_market_data()

    cached = _load_cache()

    if cached is not None:
        return cached

    return refresh_market_data()


# =========================================================
# HEALTH
# =========================================================

def market_data_health() -> dict:
    """
    Return health information for the market-data service.
    """

    cache = _load_cache()

    if not cache:

        return {
            "service": (
                "jumuiya_biashara_market_data"
            ),
            "status": UNAVAILABLE,
            "cache_exists": False,
            "cache_file": str(
                CACHE_FILE
            ),
            "development_insecure_tls": (
                _insecure_tls_enabled()
            ),
            "sources": {
                "kamis": False,
                "epra": False,
                "knbs_cpi": False,
            },
        }

    sources = cache.get(
        "sources",
        {},
    )

    return {
        "service": (
            "jumuiya_biashara_market_data"
        ),
        "status": cache.get(
            "source_status",
            UNAVAILABLE,
        ),
        "cache_exists": True,
        "cache_file": str(
            CACHE_FILE
        ),
        "last_updated": cache.get(
            "generated_at"
        ),
        "development_insecure_tls": (
            _insecure_tls_enabled()
        ),
        "sources": {
            "kamis": (
                sources.get(
                    "kamis",
                    {},
                ).get(
                    "status"
                )
                in {
                    LIVE,
                    PARTIAL,
                }
            ),
            "epra": (
                sources.get(
                    "epra",
                    {},
                ).get(
                    "status"
                )
                in {
                    LIVE,
                    PARTIAL,
                }
            ),
            "knbs_cpi": (
                sources.get(
                    "knbs_cpi",
                    {},
                ).get(
                    "status"
                )
                in {
                    LIVE,
                    PARTIAL,
                }
            ),
        },
    }


# =========================================================
# SOURCE-SPECIFIC PUBLIC HELPERS
# =========================================================

def get_live_kamis_data() -> dict:
    """
    Fetch KAMIS directly without changing the cache.
    """

    return fetch_kamis()


def get_live_epra_data() -> dict:
    """
    Fetch EPRA directly without changing the cache.
    """

    return fetch_epra()


def get_live_knbs_data() -> dict:
    """
    Fetch KNBS CPI directly without changing the cache.
    """

    return fetch_knbs()


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "fetch_url",
    "fetch_kamis",
    "fetch_epra",
    "fetch_knbs",
    "refresh_market_data",
    "get_market_signals",
    "market_data_health",
    "get_live_kamis_data",
    "get_live_epra_data",
    "get_live_knbs_data",
]