# backend/study/import_sda_q3_2026.py

"""
SDA Sabbath School Q3 2026 importer.

Quarter:
    First and Second Corinthians

Quarter:
    Q3 2026

Source:
    https://www.sabbath.school/LessonBook?quarter=3&year=2026

Pipeline:

    lesson page
        ↓
    lesson metadata
        ↓
    Lesson PDF
        ↓
    PDF text extraction
        ↓
    Saturday-Friday sections
        ↓
    SDAQuarterlyService
        ↓
    MongoDB study_materials

Run:

    python -m backend.study.import_sda_q3_2026

Optional:

    python -m backend.study.import_sda_q3_2026 --lesson 8

Dry run:

    python -m backend.study.import_sda_q3_2026 --dry-run
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import sys
from datetime import date, timedelta
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

from backend.study.sda_quarterly_service import (
    SDAQuarterlyService,
)


# =========================================================
# CONFIGURATION
# =========================================================

YEAR = 2026
QUARTER = 3

BOOK_TITLE = (
    "First and Second Corinthians"
)

SOURCE_NAME = (
    "Sabbath School"
)

BASE_URL = (
    "https://www.sabbath.school"
)

QUARTER_URL = (
    f"{BASE_URL}/LessonBook"
    f"?quarter={QUARTER}"
    f"&year={YEAR}"
)

LESSON_URL_TEMPLATE = (
    f"{BASE_URL}/Lesson"
    "?lesson={lesson}"
    f"&quarter={QUARTER}"
    f"&year={YEAR}"
)

# Q3 2026 begins Saturday, June 27.
QUARTER_START = date(
    2026,
    6,
    27,
)

LESSON_COUNT = 13

DAYS = [
    "Saturday",
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
]

DAY_OFFSETS = {
    day: index
    for index, day in enumerate(DAYS)
}


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "[%(levelname)s] "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "sda_q3_2026_importer"
)


# =========================================================
# HTTP SESSION
# =========================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "RevelaCode Study Importer/1.0 "
        "(SDA Quarterly Integration)"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/pdf;q=0.9,*/*;q=0.8"
    ),
})


# =========================================================
# HTTP HELPERS
# =========================================================

def fetch_url(
    url: str,
    *,
    timeout: int = 60,
) -> requests.Response:

    logger.info(
        "🌐 Fetching: %s",
        url,
    )

    response = SESSION.get(
        url,
        timeout=timeout,
    )

    response.raise_for_status()

    return response


# =========================================================
# LESSON URL
# =========================================================

def lesson_url(
    lesson_number: int,
) -> str:

    return LESSON_URL_TEMPLATE.format(
        lesson=lesson_number,
    )


# =========================================================
# DATE HELPERS
# =========================================================

def lesson_week_start(
    lesson_number: int,
) -> date:

    return (
        QUARTER_START
        + timedelta(
            days=(lesson_number - 1) * 7
        )
    )


def lesson_week_end(
    lesson_number: int,
) -> date:

    return (
        lesson_week_start(
            lesson_number
        )
        + timedelta(days=6)
    )


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(
    value: str,
) -> str:

    value = (
        value or ""
    )

    value = value.replace(
        "\xa0",
        " ",
    )

    value = re.sub(
        r"[ \t]+",
        " ",
        value,
    )

    value = re.sub(
        r"\n{3,}",
        "\n\n",
        value,
    )

    return value.strip()


# =========================================================
# LESSON METADATA
# =========================================================

def parse_lesson_metadata(
    html: str,
    lesson_number: int,
) -> Dict:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # -----------------------------------------------------
    # Title
    # -----------------------------------------------------

    title = ""

    for heading in soup.find_all(
        ["h1", "h2", "h3"]
    ):
        text = clean_text(
            heading.get_text(
                " ",
                strip=True,
            )
        )

        match = re.search(
            rf"Lesson\s+{lesson_number}\s*[-–—]\s*(.+)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            title = clean_text(
                match.group(1)
            )
            break

    if not title:
        title = (
            f"Lesson {lesson_number}"
        )

    # -----------------------------------------------------
    # Memory text
    # -----------------------------------------------------

    memory_text = ""

    for heading in soup.find_all(
        ["h2", "h3", "strong"]
    ):
        heading_text = clean_text(
            heading.get_text(
                " ",
                strip=True,
            )
        ).lower()

        if "memory text" not in heading_text:
            continue

        parent = heading.parent

        if parent:
            memory_text = clean_text(
                parent.get_text(
                    " ",
                    strip=True,
                )
            )

        break

    # Fallback:
    # search blockquote text.

    if not memory_text:

        blockquote = soup.find(
            "blockquote"
        )

        if blockquote:
            memory_text = clean_text(
                blockquote.get_text(
                    " ",
                    strip=True,
                )
            )

    # -----------------------------------------------------
    # Study week
    # -----------------------------------------------------

    week_text = ""

    page_text = clean_text(
        soup.get_text(
            "\n",
            strip=True,
        )
    )

    week_match = re.search(
        r"Study\s+week:\s*(.+)",
        page_text,
        flags=re.IGNORECASE,
    )

    if week_match:
        week_text = clean_text(
            week_match.group(1)
        )

    return {
        "lesson_number": lesson_number,
        "lesson_title": title,
        "memory_text": memory_text,
        "week_label": week_text,
        "week_start": (
            lesson_week_start(
                lesson_number
            ).isoformat()
        ),
        "week_end": (
            lesson_week_end(
                lesson_number
            ).isoformat()
        ),
    }


# =========================================================
# FIND LESSON PDF
# =========================================================

def find_lesson_pdf_url(
    html: str,
) -> Optional[str]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates = []

    for anchor in soup.find_all(
        "a",
        href=True,
    ):

        text = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        href = (
            anchor.get(
                "href"
            )
            or ""
        ).strip()

        combined = (
            f"{text} {href}"
        ).lower()

        if (
            "lesson pdf"
            in combined
            or (
                ".pdf"
                in href.lower()
                and "teacher"
                not in combined
                and "egw"
                not in combined
            )
        ):

            absolute = urljoin(
                BASE_URL,
                href,
            )

            candidates.append(
                absolute
            )

    # Prefer explicit Lesson PDF.

    for candidate in candidates:
        if ".pdf" in candidate.lower():
            return candidate

    return (
        candidates[0]
        if candidates
        else None
    )


# =========================================================
# DOWNLOAD PDF
# =========================================================

def download_pdf(
    pdf_url: str,
) -> bytes:

    logger.info(
        "📘 Downloading lesson PDF: %s",
        pdf_url,
    )

    response = fetch_url(
        pdf_url,
        timeout=120,
    )

    content_type = (
        response.headers.get(
            "content-type",
            "",
        ).lower()
    )

    if (
        "pdf" not in content_type
        and not response.content.startswith(
            b"%PDF"
        )
    ):
        raise ValueError(
            "Expected PDF but received "
            f"{content_type or 'unknown content'}."
        )

    return response.content


# =========================================================
# PDF TEXT EXTRACTION
# =========================================================

def extract_pdf_text(
    pdf_bytes: bytes,
) -> str:

    logger.info(
        "📖 Extracting PDF text..."
    )

    reader = PdfReader(
        io.BytesIO(
            pdf_bytes
        )
    )

    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):

        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning(
                "⚠ PDF page %d extraction failed: %s",
                page_number,
                exc,
            )
            continue

        text = clean_text(
            text
        )

        if text:
            pages.append(text)

    if not pages:
        raise ValueError(
            "PDF text extraction returned no text."
        )

    return "\n\n".join(
        pages
    )


# =========================================================
# DAY HEADING DETECTION
# =========================================================

def find_day_headings(
    text: str,
) -> List[Dict]:

    """
    Detect Saturday-Friday headings.

    We intentionally handle several variants:

        Saturday
        SATURDAY
        Saturday:
        Saturday — June 15
        Sunday — June 16
        Monday:
    """

    day_pattern = re.compile(
        r"(?im)"
        r"^(?P<day>"
        r"Saturday|Sunday|Monday|"
        r"Tuesday|Wednesday|Thursday|Friday"
        r")"
        r"(?:\s*[:\-–—]\s*.*)?$"
    )

    matches = []

    for match in day_pattern.finditer(
        text
    ):

        day = match.group(
            "day"
        )

        matches.append({
            "day": day,
            "start": match.start(),
            "end": match.end(),
        })

    return matches


# =========================================================
# SPLIT DAILY CONTENT
# =========================================================

def split_daily_content(
    text: str,
) -> Dict[str, str]:

    headings = find_day_headings(
        text
    )

    # -----------------------------------------------------
    # Deduplicate repeated headings
    # -----------------------------------------------------

    unique = []

    seen_days = set()

    for heading in headings:

        day = heading["day"]

        if day in seen_days:
            continue

        seen_days.add(day)
        unique.append(heading)

    headings = unique

    if len(headings) < 7:
        raise ValueError(
            "Could not confidently identify "
            "all seven daily lesson sections. "
            f"Detected {len(headings)}."
        )

    sections = {}

    for index, heading in enumerate(
        headings
    ):

        day = heading["day"]

        start = heading["end"]

        if index + 1 < len(headings):
            end = headings[
                index + 1
            ]["start"]
        else:
            end = len(text)

        content = clean_text(
            text[start:end]
        )

        sections[day] = content

    missing = [
        day
        for day in DAYS
        if day not in sections
    ]

    if missing:
        raise ValueError(
            "Missing daily sections: "
            + ", ".join(missing)
        )

    return sections


# =========================================================
# BUILD LESSON
# =========================================================

def build_lesson_payload(
    lesson_number: int,
) -> Dict:

    page_url = lesson_url(
        lesson_number
    )

    page_response = fetch_url(
        page_url
    )

    html = page_response.text

    metadata = parse_lesson_metadata(
        html,
        lesson_number,
    )

    pdf_url = find_lesson_pdf_url(
        html
    )

    if not pdf_url:
        raise ValueError(
            "Could not locate Lesson PDF."
        )

    pdf_bytes = download_pdf(
        pdf_url
    )

    full_text = extract_pdf_text(
        pdf_bytes
    )

    daily_sections = split_daily_content(
        full_text
    )

    week_start = lesson_week_start(
        lesson_number
    )

    days = []

    for day_name in DAYS:

        day_date = (
            week_start
            + timedelta(
                days=DAY_OFFSETS[
                    day_name
                ]
            )
        )

        content = daily_sections[
            day_name
        ]

        days.append({
            "day": day_name,
            "date": day_date.isoformat(),
            "title": metadata[
                "lesson_title"
            ],
            "content": content,
            "source_url": page_url,
            "pdf_url": pdf_url,
            "tags": [
                "SDA",
                "Sabbath School",
                "Quarterly",
                "Q3",
                "2026",
                f"Lesson {lesson_number}",
                day_name,
            ],
            "ai_enabled": True,
        })

    return {
        "year": YEAR,
        "quarter": QUARTER,
        "label": "Q3 2026",
        "book_title": BOOK_TITLE,
        "source_name": SOURCE_NAME,
        "source_url": QUARTER_URL,
        "lessons": [
            {
                **metadata,
                "source_url": page_url,
                "pdf_url": pdf_url,
                "days": days,
            }
        ],
    }


# =========================================================
# IMPORT LESSON
# =========================================================

def import_lesson(
    lesson_number: int,
    *,
    dry_run: bool = False,
) -> Dict:

    logger.info(
        "=============================================="
    )

    logger.info(
        "📚 Importing SDA Q3 2026 Lesson %d",
        lesson_number,
    )

    payload = build_lesson_payload(
        lesson_number
    )

    lesson = payload[
        "lessons"
    ][0]

    logger.info(
        "✅ Lesson: %s",
        lesson.get(
            "lesson_title"
        ),
    )

    logger.info(
        "📅 Week: %s → %s",
        lesson.get(
            "week_start"
        ),
        lesson.get(
            "week_end"
        ),
    )

    logger.info(
        "📄 Daily sections: %d",
        len(
            lesson.get(
                "days",
                []
            )
        ),
    )

    if dry_run:

        for day in lesson["days"]:

            logger.info(
                "DRY RUN | %s | %s | %d chars",
                day["date"],
                day["day"],
                len(
                    day["content"]
                ),
            )

        return {
            "success": True,
            "dry_run": True,
            "lesson": lesson,
        }

    result = (
        SDAQuarterlyService
        .import_quarter(
            payload
        )
    )

    return result


# =========================================================
# IMPORT ALL Q3
# =========================================================

def import_q3(
    *,
    lesson_number: Optional[int] = None,
    dry_run: bool = False,
) -> Dict:

    lesson_numbers = (
        [lesson_number]
        if lesson_number
        else list(
            range(
                1,
                LESSON_COUNT + 1
            )
        )
    )

    results = []

    for number in lesson_numbers:

        try:

            result = import_lesson(
                number,
                dry_run=dry_run,
            )

            results.append(
                {
                    "lesson": number,
                    "success": True,
                    "result": result,
                }
            )

        except Exception as exc:

            logger.exception(
                "❌ Lesson %d failed",
                number,
            )

            results.append(
                {
                    "lesson": number,
                    "success": False,
                    "error": str(exc),
                }
            )

    successful = sum(
        1
        for item in results
        if item["success"]
    )

    failed = (
        len(results)
        - successful
    )

    return {
        "success": failed == 0,
        "year": YEAR,
        "quarter": QUARTER,
        "lessons_requested": len(
            results
        ),
        "successful": successful,
        "failed": failed,
        "results": results,
    }


# =========================================================
# CLI
# =========================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Import SDA Sabbath School "
            "Q3 2026 into study_materials."
        )
    )

    parser.add_argument(
        "--lesson",
        type=int,
        choices=range(
            1,
            LESSON_COUNT + 1
        ),
        help=(
            "Import one lesson only."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Extract and validate without "
            "writing to MongoDB."
        ),
    )

    return parser.parse_args()


# =========================================================
# MAIN
# =========================================================

def main():

    args = parse_args()

    result = import_q3(
        lesson_number=args.lesson,
        dry_run=args.dry_run,
    )

    print()
    print(
        "=============================================="
    )
    print(
        "SDA Q3 2026 IMPORT COMPLETE"
    )
    print(
        "=============================================="
    )

    print(
        f"Lessons requested : "
        f"{result['lessons_requested']}"
    )

    print(
        f"Successful         : "
        f"{result['successful']}"
    )

    print(
        f"Failed             : "
        f"{result['failed']}"
    )

    print(
        f"Success            : "
        f"{result['success']}"
    )

    if result["failed"]:

        print()
        print(
            "Failed lessons:"
        )

        for item in result[
            "results"
        ]:

            if not item["success"]:

                print(
                    f"  Lesson {item['lesson']}: "
                    f"{item['error']}"
                )

        sys.exit(1)


if __name__ == "__main__":
    main()
