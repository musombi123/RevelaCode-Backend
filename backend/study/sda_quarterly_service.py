# backend/study/sda_quarterly_service.py

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from backend.db import get_db


class SDAQuarterlyService:
    """
    Stores SDA Sabbath School quarterly lessons as normal
    StudyMaterial documents.

    The service is intentionally source-agnostic:
    - upstream source supplies structured lesson data
    - this service normalizes it
    - MongoDB stores one record per daily lesson

    Expected lesson payload:

    {
        "lesson_number": 8,
        "lesson_title": "The Power of Christ's Resurrection",
        "quarter": 3,
        "year": 2026,
        "week_start": "2026-08-15",
        "week_end": "2026-08-21",
        "memory_text": "...",
        "days": [
            {
                "day": "Saturday",
                "date": "2026-08-15",
                "title": "The Weekly Lesson",
                "content": "..."
            },
            ...
        ]
    }
    """

    COLLECTION = "study_materials"

    CATEGORY = "faith"
    SUBCATEGORY = "sda_quarterly"
    MATERIAL_TYPE = "lesson"

    SOURCE_NAME = "SDA Sabbath School"

    # =====================================================
    # DATE HELPERS
    # =====================================================

    @staticmethod
    def parse_date(value: Any) -> Optional[date]:
        if isinstance(value, date):
            return value

        if not value:
            return None

        text = str(value).strip()

        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%m/%d/%Y",
        ):
            try:
                return datetime.strptime(
                    text,
                    fmt,
                ).date()
            except ValueError:
                continue

        return None

    @staticmethod
    def format_date(value: Optional[date]) -> Optional[str]:
        if not value:
            return None

        return value.isoformat()

    # =====================================================
    # SAFE STRING
    # =====================================================

    @staticmethod
    def clean_string(value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()

    # =====================================================
    # WEEK DAYS
    # =====================================================

    @staticmethod
    def generate_week_dates(
        week_start: date,
    ) -> List[date]:
        """
        Generate the seven Sabbath-week dates.

        Sabbath is treated as day 0:
        Saturday → Friday.
        """

        return [
            week_start + timedelta(days=i)
            for i in range(7)
        ]

    # =====================================================
    # MATERIAL DOCUMENT
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
                lesson.get("year"),
            )
        )

        quarter_number = int(
            quarter.get(
                "quarter",
                lesson.get("quarter"),
            )
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

        lesson_title = (
            cls.clean_string(
                lesson.get(
                    "lesson_title"
                )
            )
        )

        day_name = (
            cls.clean_string(
                day_item.get(
                    "day"
                )
            )
        )

        lesson_date = cls.parse_date(
            day_item.get(
                "date"
            )
        )

        if not lesson_date:
            raise ValueError(
                "Each SDA daily lesson must have a valid date."
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

        content = (
            cls.clean_string(
                day_item.get(
                    "content"
                )
            )
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
            quarter.get(
                "label"
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

        metadata = {
            "program": cls.SOURCE_NAME,
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
            "memory_text": memory_text,
            "source_url": source_url,
            "source_name": cls.SOURCE_NAME,
            "is_daily_lesson": True,
        }

        tags = [
            "SDA",
            "Sabbath School",
            "quarterly",
            f"Q{quarter_number}",
            str(year),
            f"Lesson {lesson_number}",
            day_name,
        ]

        # Add optional source tags.
        extra_tags = day_item.get(
            "tags"
        ) or lesson.get(
            "tags"
        ) or []

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

        material = {
            "title": (
                f"{day_name} — "
                f"{daily_title}"
                if day_name
                else daily_title
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
            "created_at": (
                datetime.utcnow()
                .isoformat()
            ),
            "updated_at": (
                datetime.utcnow()
                .isoformat()
            ),
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

        lesson_date = (
            material.get(
                "metadata",
                {}
            ).get(
                "lesson_date"
            )
        )

        lesson_number = (
            material.get(
                "metadata",
                {}
            ).get(
                "lesson_number"
            )
        )

        year = material.get(
            "year"
        )

        quarter = (
            material.get(
                "metadata",
                {}
            ).get(
                "quarter"
            )
        )

        existing_filter = {
            "subcategory": cls.SUBCATEGORY,
            "year": year,
            "metadata.lesson_date": lesson_date,
            "metadata.lesson_number": lesson_number,
            "metadata.quarter": quarter,
        }

        existing = db[
            cls.COLLECTION
        ].find_one(
            existing_filter
        )

        now = (
            datetime.utcnow()
            .isoformat()
        )

        if existing:
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

            # Keep the public id if it already exists.
            if existing.get("id"):
                material["id"] = existing["id"]

            return {
                "success": True,
                "action": "updated",
                "material": material,
            }

        # -----------------------------------------------
        # New material
        # -----------------------------------------------

        import uuid

        material["id"] = str(
            uuid.uuid4()
        )

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
            []
        )

        if not isinstance(
            days,
            list,
        ):
            raise ValueError(
                "Lesson 'days' must be a list."
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
            []
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
            or date.today()
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
            or date.today()
        )

        # Sabbath-based week:
        # Saturday through Friday.

        days_since_saturday = (
            target_date.weekday() + 2
        ) % 7

        week_start = (
            target_date -
            timedelta(
                days=days_since_saturday
            )
        )

        week_end = (
            week_start +
            timedelta(days=6)
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
                    ""
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
                    ""
                ),
            )
        )

        return materials
