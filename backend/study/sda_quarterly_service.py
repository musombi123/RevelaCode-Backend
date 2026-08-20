# backend/study/sda_quarterly_service.py

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import uuid

from backend.db import get_db


class SDAQuarterlyService:
    """
    Stores SDA Sabbath School quarterly lessons as
    normal StudyMaterial documents.

    One daily lesson = one study_materials document.

    Example:

        category       = faith
        subcategory    = sda_quarterly
        material_type  = lesson

    SDA-specific information lives inside metadata.
    """

    COLLECTION = "study_materials"

    CATEGORY = "faith"
    SUBCATEGORY = "sda_quarterly"
    MATERIAL_TYPE = "lesson"

    SOURCE_NAME = "SDA Sabbath School"

    TIMEZONE = ZoneInfo(
        "Africa/Nairobi"
    )

    # =====================================================
    # DATE HELPERS
    # =====================================================

    @staticmethod
    def parse_date(
        value: Any,
    ) -> Optional[date]:

        if isinstance(
            value,
            datetime,
        ):
            return value.date()

        if isinstance(
            value,
            date,
        ):
            return value

        if not value:
            return None

        text = str(value).strip()

        formats = (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%m/%d/%Y",
        )

        for fmt in formats:

            try:
                return datetime.strptime(
                    text,
                    fmt,
                ).date()

            except ValueError:
                continue

        return None

    @classmethod
    def today_date(cls) -> date:
        """
        Return today's date in Kenya.
        """
        return datetime.now(
            cls.TIMEZONE
        ).date()

    @staticmethod
    def format_date(
        value: Optional[date],
    ) -> Optional[str]:

        if not value:
            return None

        return value.isoformat()

    # =====================================================
    # SAFE STRING
    # =====================================================

    @staticmethod
    def clean_string(
        value: Any,
    ) -> str:

        if value is None:
            return ""

        return str(
            value
        ).strip()

    # =====================================================
    # WEEK DAYS
    # =====================================================

    @staticmethod
    def generate_week_dates(
        week_start: date,
    ) -> List[date]:

        return [
            week_start +
            timedelta(days=i)
            for i in range(7)
        ]

    # =====================================================
    # DETERMINISTIC KEY
    # =====================================================

    @classmethod
    def build_lesson_key(
        cls,
        year: int,
        quarter: int,
        lesson_number: int,
        day_name: str,
    ) -> str:

        normalized_day = (
            cls.clean_string(
                day_name
            )
            .lower()
            .replace(" ", "-")
        )

        return (
            f"sda-{year}"
            f"-q{quarter}"
            f"-l{lesson_number}"
            f"-{normalized_day}"
        )

    # =====================================================
    # BUILD MATERIAL
    # =====================================================

    @classmethod
    def build_daily_material(
        cls,
        quarter: Dict[str, Any],
        lesson: Dict[str, Any],
        day_item: Dict[str, Any],
    ) -> Dict[str, Any]:

        year = int(
            quarter.get(
                "year",
                lesson.get(
                    "year",
                    0,
                ),
            )
        )

        quarter_number = int(
            quarter.get(
                "quarter",
                lesson.get(
                    "quarter",
                    0,
                ),
            )
        )

        if not year:
            raise ValueError(
                "SDA lesson year is required."
            )

        if not quarter_number:
            raise ValueError(
                "SDA quarter number is required."
            )

        lesson_number = int(
            lesson.get(
                "lesson_number",
                day_item.get(
                    "lesson_number",
                    0,
                ),
            )
        )

        if not lesson_number:
            raise ValueError(
                "SDA lesson number is required."
            )

        lesson_title = cls.clean_string(
            lesson.get(
                "lesson_title"
            )
        )

        day_name = cls.clean_string(
            day_item.get(
                "day"
            )
        )

        if not day_name:
            raise ValueError(
                "SDA daily lesson day is required."
            )

        lesson_date = cls.parse_date(
            day_item.get(
                "date"
            )
        )

        if not lesson_date:
            raise ValueError(
                "Each SDA daily lesson must have "
                "a valid date."
            )

        daily_title = (
            cls.clean_string(
                day_item.get(
                    "title"
                )
            )
            or lesson_title
            or f"Lesson {lesson_number}"
        )

        content = cls.clean_string(
            day_item.get(
                "content"
            )
        )

        if not content:
            raise ValueError(
                f"SDA lesson content is empty for "
                f"{day_name}."
            )

        memory_text = (
            cls.clean_string(
                day_item.get(
                    "memory_text"
                )
            )
            or cls.clean_string(
                lesson.get(
                    "memory_text"
                )
            )
        )

        quarter_label = (
            cls.clean_string(
                quarter.get(
                    "label"
                )
            )
            or f"Q{quarter_number} {year}"
        )

        source_url = (
            day_item.get(
                "source_url"
            )
            or lesson.get(
                "source_url"
            )
            or quarter.get(
                "source_url"
            )
        )

        pdf_url = (
            day_item.get(
                "pdf_url"
            )
            or lesson.get(
                "pdf_url"
            )
        )

        lesson_key = (
            cls.build_lesson_key(
                year,
                quarter_number,
                lesson_number,
                day_name,
            )
        )

        metadata = {
            "program": cls.SOURCE_NAME,
            "lesson_key": lesson_key,
            "lesson_number": lesson_number,
            "lesson_title": lesson_title,
            "day": day_name,
            "lesson_date": lesson_date.isoformat(),
            "week_start": cls.clean_string(
                lesson.get(
                    "week_start"
                )
            ),
            "week_end": cls.clean_string(
                lesson.get(
                    "week_end"
                )
            ),
            "quarter": quarter_number,
            "quarter_label": quarter_label,
            "year": year,
            "book_title": (
                quarter.get(
                    "book_title"
                )
                or "SDA Sabbath School"
            ),
            "memory_text": memory_text,
            "source_url": source_url,
            "pdf_url": pdf_url,
            "source_name": cls.SOURCE_NAME,
            "is_daily_lesson": True,
        }

        tags = [
            "SDA",
            "Sabbath School",
            "Quarterly",
            f"Q{quarter_number}",
            str(year),
            f"Lesson {lesson_number}",
            day_name,
        ]

        extra_tags = (
            day_item.get(
                "tags"
            )
            or lesson.get(
                "tags"
            )
            or []
        )

        if isinstance(
            extra_tags,
            list,
        ):

            tags.extend(
                [
                    cls.clean_string(tag)
                    for tag in extra_tags
                    if cls.clean_string(tag)
                ]
            )

        now = datetime.utcnow().isoformat()

        material = {
            "id": lesson_key,

            "title": (
                f"{day_name} — "
                f"{daily_title}"
            ),

            "category": cls.CATEGORY,

            "subcategory": cls.SUBCATEGORY,

            "material_type": cls.MATERIAL_TYPE,

            "content": content,

            "file_path": None,

            "year": year,

            "author": (
                lesson.get(
                    "author"
                )
                or cls.SOURCE_NAME
            ),

            "tags": sorted(
                set(tags)
            ),

            "metadata": metadata,

            "ai_enabled": bool(
                day_item.get(
                    "ai_enabled",
                    True,
                )
            ),

            "created_at": now,

            "updated_at": now,
        }

        return material

    # =====================================================
    # UPSERT DAILY LESSON
    # =====================================================

    @classmethod
    def upsert_daily_lesson(
        cls,
        material: Dict[str, Any],
    ) -> Dict[str, Any]:

        db = get_db()

        lesson_key = (
            material.get(
                "metadata",
                {}
            ).get(
                "lesson_key"
            )
        )

        if not lesson_key:
            raise ValueError(
                "SDA material is missing lesson_key."
            )

        existing = db[
            cls.COLLECTION
        ].find_one(
            {
                "id": lesson_key,
            }
        )

        now = datetime.utcnow().isoformat()

        if existing:

            # Preserve original creation date.
            material["created_at"] = (
                existing.get(
                    "created_at"
                )
                or now
            )

            material["updated_at"] = now

            db[
                cls.COLLECTION
            ].update_one(
                {
                    "_id": existing["_id"]
                },
                {
                    "$set": material
                },
            )

            material["_id"] = str(
                existing["_id"]
            )

            return {
                "success": True,
                "action": "updated",
                "material": material,
            }

        # -------------------------------------------------
        # CREATE
        # -------------------------------------------------

        material["created_at"] = now
        material["updated_at"] = now

        result = db[
            cls.COLLECTION
        ].insert_one(
            material
        )

        material["_id"] = str(
            result.inserted_id
        )

        return {
            "success": True,
            "action": "created",
            "material": material,
        }

    # =====================================================
    # IMPORT ONE LESSON
    # =====================================================

    @classmethod
    def import_lesson(
        cls,
        quarter: Dict[str, Any],
        lesson: Dict[str, Any],
    ) -> Dict[str, Any]:

        days = lesson.get(
            "days",
            [],
        )

        if not isinstance(
            days,
            list,
        ):
            raise ValueError(
                "Lesson 'days' must be a list."
            )

        # -------------------------------------------------
        # STRICT VALIDATION
        # -------------------------------------------------

        required_days = {
            "Saturday",
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
        }

        received_days = {
            cls.clean_string(
                item.get(
                    "day"
                )
            )
            for item in days
            if isinstance(
                item,
                dict,
            )
        }

        missing = (
            required_days
            - received_days
        )

        if missing:

            raise ValueError(
                "SDA lesson is incomplete. "
                "Missing days: "
                + ", ".join(
                    sorted(missing)
                )
            )

        results = []

        for day_item in days:

            if not isinstance(
                day_item,
                dict,
            ):
                continue

            material = (
                cls.build_daily_material(
                    quarter,
                    lesson,
                    day_item,
                )
            )

            result = (
                cls.upsert_daily_lesson(
                    material
                )
            )

            results.append(
                result
            )

        return {
            "success": True,
            "lesson_number": lesson.get(
                "lesson_number"
            ),
            "lesson_title": lesson.get(
                "lesson_title"
            ),
            "days_processed": len(
                results
            ),
            "results": results,
        }

    # =====================================================
    # IMPORT QUARTER
    # =====================================================

    @classmethod
    def import_quarter(
        cls,
        quarter: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not isinstance(
            quarter,
            dict,
        ):
            raise ValueError(
                "Quarter payload must be an object."
            )

        year = quarter.get(
            "year"
        )

        quarter_number = quarter.get(
            "quarter"
        )

        lessons = quarter.get(
            "lessons",
            [],
        )

        if not year:
            raise ValueError(
                "Quarter year is required."
            )

        if not quarter_number:
            raise ValueError(
                "Quarter number is required."
            )

        if not isinstance(
            lessons,
            list,
        ):
            raise ValueError(
                "Quarter lessons must be a list."
            )

        processed = []

        for lesson in lessons:

            if not isinstance(
                lesson,
                dict,
            ):
                continue

            processed.append(
                cls.import_lesson(
                    quarter,
                    lesson,
                )
            )

        total_days = sum(
            item.get(
                "days_processed",
                0,
            )
            for item in processed
        )

        return {
            "success": True,
            "year": int(year),
            "quarter": int(
                quarter_number
            ),
            "lessons_processed": len(
                processed
            ),
            "days_processed": total_days,
            "lessons": processed,
        }

    # =====================================================
    # TODAY
    # =====================================================

    @classmethod
    def get_today(
        cls,
        target_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:

        db = get_db()

        target_date = (
            target_date
            or cls.today_date()
        )

        material = db[
            cls.COLLECTION
        ].find_one(
            {
                "subcategory":
                    cls.SUBCATEGORY,
                "metadata.lesson_date":
                    target_date.isoformat(),
            }
        )

        if not material:
            return None

        if material.get("_id"):
            material["_id"] = str(
                material["_id"]
            )

        return material

    # =====================================================
    # BY DATE
    # =====================================================

    @classmethod
    def get_by_date(
        cls,
        target_date: date,
    ) -> Optional[Dict[str, Any]]:

        return cls.get_today(
            target_date
        )

    # =====================================================
    # CURRENT WEEK
    # =====================================================

    @classmethod
    def get_current_week(
        cls,
        target_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:

        target_date = (
            target_date
            or cls.today_date()
        )

        # Python:
        # Monday = 0
        # Sunday = 6
        #
        # We want Saturday = start.

        days_since_saturday = (
            target_date.weekday() + 2
        ) % 7

        week_start = (
            target_date
            - timedelta(
                days=days_since_saturday
            )
        )

        week_end = (
            week_start
            + timedelta(
                days=6
            )
        )

        db = get_db()

        materials = list(
            db[
                cls.COLLECTION
            ].find(
                {
                    "subcategory":
                        cls.SUBCATEGORY,
                    "metadata.lesson_date": {
                        "$gte":
                            week_start.isoformat(),
                        "$lte":
                            week_end.isoformat(),
                    },
                }
            )
        )

        for material in materials:

            if material.get("_id"):
                material["_id"] = str(
                    material["_id"]
                )

        materials.sort(
            key=lambda item:
                item.get(
                    "metadata",
                    {}
                ).get(
                    "lesson_date",
                    "",
                )
        )

        return materials

    # =====================================================
    # QUARTER
    # =====================================================

    @classmethod
    def get_quarter(
        cls,
        year: int,
        quarter: int,
    ) -> List[Dict[str, Any]]:

        db = get_db()

        materials = list(
            db[
                cls.COLLECTION
            ].find(
                {
                    "subcategory":
                        cls.SUBCATEGORY,
                    "year": int(year),
                    "metadata.quarter":
                        int(quarter),
                }
            )
        )

        for material in materials:

            if material.get("_id"):
                material["_id"] = str(
                    material["_id"]
                )

        materials.sort(
            key=lambda item: (
                item.get(
                    "metadata",
                    {}
                ).get(
                    "lesson_number",
                    0,
                ),
                item.get(
                    "metadata",
                    {}
                ).get(
                    "lesson_date",
                    "",
                ),
            )
        )

        return materials
