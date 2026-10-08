# backend/jumuiya/elimu/reports/models.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


# =========================================================
# REPORT COLLECTIONS
# =========================================================

EXAM_REPORTS = "jumuiya_elimu_exam_reports"
PROGRAMMES = "jumuiya_elimu_school_programmes"
SCHOOL_CURRICULA = "jumuiya_elimu_school_curricula"


# =========================================================
# SCHEMA VERSION
# =========================================================

REPORT_SCHEMA_VERSION = "2.0"


# =========================================================
# EDUCATION LEVELS
# =========================================================

EDUCATION_PRE_PRIMARY = "pre_primary"
EDUCATION_PRIMARY = "primary"
EDUCATION_JUNIOR_SCHOOL = "junior_school"
EDUCATION_SENIOR_SCHOOL = "senior_school"
EDUCATION_SNE = "sne"

EDUCATION_LEVELS = (
    EDUCATION_PRE_PRIMARY,
    EDUCATION_PRIMARY,
    EDUCATION_JUNIOR_SCHOOL,
    EDUCATION_SENIOR_SCHOOL,
    EDUCATION_SNE,
)


# =========================================================
# CURRICULUM FRAMEWORK
# =========================================================

FRAMEWORK_CBC = "cbc"
FRAMEWORK_SCHOOL_INTERNAL = "school_internal"
FRAMEWORK_HYBRID = "hybrid"

CURRICULUM_FRAMEWORKS = (
    FRAMEWORK_CBC,
    FRAMEWORK_SCHOOL_INTERNAL,
    FRAMEWORK_HYBRID,
)


# =========================================================
# SENIOR SCHOOL PATHWAYS
# =========================================================
#
# These reflect the current CBC senior-school pathway structure.
# Keep this catalog configurable because official curriculum
# structures can evolve.
#
# =========================================================

PATHWAY_STEM = "stem"
PATHWAY_SOCIAL_SCIENCES = "social_sciences"
PATHWAY_ARTS_SPORTS = "arts_and_sports_science"

SENIOR_SCHOOL_PATHWAYS = (
    PATHWAY_STEM,
    PATHWAY_SOCIAL_SCIENCES,
    PATHWAY_ARTS_SPORTS,
)


# =========================================================
# SENIOR SCHOOL CORE LEARNING AREA GROUPS
# =========================================================

SENIOR_CORE_ENGLISH = "english"
SENIOR_CORE_KISWAHILI_KSL = "kiswahili_ksl"
SENIOR_CORE_MATHEMATICS = "mathematics"
SENIOR_CORE_CSL = "community_service_learning"

SENIOR_CORE_GROUPS = (
    SENIOR_CORE_ENGLISH,
    SENIOR_CORE_KISWAHILI_KSL,
    SENIOR_CORE_MATHEMATICS,
    SENIOR_CORE_CSL,
)


# =========================================================
# LEARNING AREA CATEGORIES
# =========================================================

CATEGORY_CORE = "core"
CATEGORY_ELECTIVE = "elective"
CATEGORY_COMPULSORY = "compulsory"
CATEGORY_OPTIONAL = "optional"
CATEGORY_ENRICHMENT = "enrichment"
CATEGORY_PATHWAY = "pathway"
CATEGORY_OTHER = "other"

LEARNING_AREA_CATEGORIES = (
    CATEGORY_CORE,
    CATEGORY_ELECTIVE,
    CATEGORY_COMPULSORY,
    CATEGORY_OPTIONAL,
    CATEGORY_ENRICHMENT,
    CATEGORY_PATHWAY,
    CATEGORY_OTHER,
)


# =========================================================
# REPORT TYPES
# =========================================================

REPORT_TYPE_SCHOOL = "school_report"
REPORT_TYPE_INDIVIDUAL_LEARNER = "individual_learner_report"
REPORT_TYPE_KJSEA_ALIGNED = "kjsea_aligned"
REPORT_TYPE_PROGRESS = "progress_report"

REPORT_TYPES = (
    REPORT_TYPE_SCHOOL,
    REPORT_TYPE_INDIVIDUAL_LEARNER,
    REPORT_TYPE_KJSEA_ALIGNED,
    REPORT_TYPE_PROGRESS,
)


# =========================================================
# REPORT STATUS
# =========================================================

REPORT_DRAFT = "draft"
REPORT_GENERATED = "generated"
REPORT_PUBLISHED = "published"
REPORT_ARCHIVED = "archived"

REPORT_STATUSES = (
    REPORT_DRAFT,
    REPORT_GENERATED,
    REPORT_PUBLISHED,
    REPORT_ARCHIVED,
)


# =========================================================
# PROGRAMME STATUS
# =========================================================

PROGRAMME_DRAFT = "draft"
PROGRAMME_GENERATED = "generated"
PROGRAMME_PUBLISHED = "published"
PROGRAMME_ARCHIVED = "archived"

PROGRAMME_STATUSES = (
    PROGRAMME_DRAFT,
    PROGRAMME_GENERATED,
    PROGRAMME_PUBLISHED,
    PROGRAMME_ARCHIVED,
)


# =========================================================
# PROGRAMME ACTIVITY TYPES
# =========================================================

ACTIVITY_TYPES = (
    "academic",
    "revision",
    "remedial",
    "guidance",
    "counselling",
    "sports",
    "co_curricular",
    "cleaning",
    "meeting",
    "assembly",
    "break",
    "lunch",
    "church",
    "career",
    "results",
    "other",
)


# =========================================================
# CBC PERFORMANCE LEVELS
# =========================================================
#
# Current KJSEA reporting uses:
#
#   EE1 = 8
#   EE2 = 7
#   ME1 = 6
#   ME2 = 5
#   AE1 = 4
#   AE2 = 3
#   BE1 = 2
#   BE2 = 1
#
# These are kept as a catalog for KJSEA-aligned reporting.
# They are NOT forced onto every internal school report.
#
# =========================================================

CBC_PERFORMANCE_LEVELS = (
    {
        "code": "EE1",
        "band": "Exceeding Expectation",
        "points": 8,
    },
    {
        "code": "EE2",
        "band": "Exceeding Expectation",
        "points": 7,
    },
    {
        "code": "ME1",
        "band": "Meeting Expectation",
        "points": 6,
    },
    {
        "code": "ME2",
        "band": "Meeting Expectation",
        "points": 5,
    },
    {
        "code": "AE1",
        "band": "Approaching Expectation",
        "points": 4,
    },
    {
        "code": "AE2",
        "band": "Approaching Expectation",
        "points": 3,
    },
    {
        "code": "BE1",
        "band": "Below Expectation",
        "points": 2,
    },
    {
        "code": "BE2",
        "band": "Below Expectation",
        "points": 1,
    },
)


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# BASIC HELPERS
# =========================================================

def _text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def _id(
    value: Any,
) -> str | None:
    normalized = _text(value)

    return normalized or None


def _string_list(
    values: Iterable[Any] | None,
) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    result: list[str] = []

    for value in values:
        normalized = _text(value)

        if normalized and normalized not in result:
            result.append(normalized)

    return result


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "1",
            "yes",
            "on",
        }:
            return True

        if normalized in {
            "false",
            "0",
            "no",
            "off",
        }:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return default


def _safe_number(
    value: Any,
) -> int | float | None:
    if value is None:
        return None

    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if number.is_integer():
        return int(number)

    return number


# =========================================================
# STUDENT SNAPSHOT
# =========================================================

def student_snapshot(
    student: Mapping[str, Any],
) -> dict:
    """
    Immutable learner identity snapshot stored in reports.
    """

    if not isinstance(student, Mapping):
        raise ValueError(
            "student must be an object."
        )

    student_id = (
        student.get("student_id")
        or student.get("_id")
    )

    return {
        "student_id": (
            str(student_id)
            if student_id is not None
            else ""
        ),

        "student_user_id": _text(
            student.get(
                "student_user_id"
            )
        ) or None,

        "student_name": _text(
            student.get(
                "full_name",
                student.get(
                    "student_name"
                ),
            )
        ),

        "admission_number": _text(
            student.get(
                "admission_number"
            )
        ),

        "student_code": _text(
            student.get(
                "student_code"
            )
        ),

        "class_id": _text(
            student.get(
                "class_id"
            )
        ) or None,

        "class_name": _text(
            student.get(
                "class_name"
            )
        ),

        "stream": _text(
            student.get(
                "stream"
            )
        ),
    }


# =========================================================
# LEARNING AREA
# =========================================================

def normalize_learning_area(
    learning_area: Mapping[str, Any],
) -> dict:
    """
    Canonical school learning-area configuration.

    A school may configure the learning areas it actually offers.
    The report generator later uses this configuration to determine
    which learning areas belong on a learner's report.
    """

    if not isinstance(
        learning_area,
        Mapping,
    ):
        raise ValueError(
            "Each learning area must be an object."
        )

    learning_area_id = _id(
        learning_area.get(
            "learning_area_id"
            or learning_area.get("course_id")
            or learning_area.get("id")
        )
    )

    name = _text(
        learning_area.get(
            "name",
            learning_area.get(
                "subject"
            ),
        )
    )

    if not learning_area_id:
        # Stable fallback for internally-created configurations.
        learning_area_id = (
            _text(name).lower()
            .replace(" ", "_")
            or None
        )

    if not learning_area_id:
        raise ValueError(
            "learning_area_id or name is required."
        )

    if not name:
        raise ValueError(
            "Learning area name is required."
        )

    code = _text(
        learning_area.get(
            "code"
        )
    ) or None

    short_name = _text(
        learning_area.get(
            "short_name"
        )
    ) or None

    category = (
        _text(
            learning_area.get(
                "category",
                CATEGORY_OTHER,
            )
        ).lower()
        or CATEGORY_OTHER
    )

    if category not in LEARNING_AREA_CATEGORIES:
        raise ValueError(
            "Invalid learning area category."
        )

    pathway = (
        _text(
            learning_area.get(
                "pathway"
            )
        ).lower()
        or None
    )

    if pathway and pathway not in SENIOR_SCHOOL_PATHWAYS:
        raise ValueError(
            "Invalid learning area pathway."
        )

    strands = []

    for strand in learning_area.get(
        "strands",
        [],
    ) or []:
        if isinstance(
            strand,
            Mapping,
        ):
            strands.append(
                {
                    "id": _id(
                        strand.get(
                            "id"
                        )
                    ),
                    "name": _text(
                        strand.get(
                            "name"
                        )
                    ),
                    "sub_strands": _string_list(
                        strand.get(
                            "sub_strands"
                        )
                    ),
                }
            )

    competencies = _string_list(
        learning_area.get(
            "competencies"
        )
    )

    return {
        "learning_area_id": learning_area_id,

        "code": code,

        "name": name,

        "short_name": short_name,

        "category": category,

        "required": _safe_bool(
            learning_area.get(
                "required"
            ),
            False,
        ),

        "selected": _safe_bool(
            learning_area.get(
                "selected"
            ),
            False,
        ),

        "assessment_enabled": _safe_bool(
            learning_area.get(
                "assessment_enabled"
            ),
            True,
        ),

        "include_in_report": _safe_bool(
            learning_area.get(
                "include_in_report"
            ),
            True,
        ),

        "report_order": _safe_int(
            learning_area.get(
                "report_order"
            ),
            0,
        ),

        "weekly_lessons": (
            _safe_int(
                learning_area.get(
                    "weekly_lessons"
                )
            )
            if learning_area.get(
                "weekly_lessons"
            ) is not None
            else None
        ),

        "pathway": pathway,

        "track": (
            _text(
                learning_area.get(
                    "track"
                )
            )
            or None
        ),

        "core_group": (
            _text(
                learning_area.get(
                    "core_group"
                )
            ).lower()
            or None
        ),

        "strands": strands,

        "competencies": competencies,

        "assessment_model": (
            _text(
                learning_area.get(
                    "assessment_model",
                    "cbc",
                )
            ).lower()
            or "cbc"
        ),

        "grading_model": (
            _text(
                learning_area.get(
                    "grading_model",
                    "performance_level",
                )
            ).lower()
            or "performance_level"
        ),

        "metadata": (
            dict(
                learning_area.get(
                    "metadata",
                    {}
                )
                or {}
            )
            if isinstance(
                learning_area.get(
                    "metadata",
                    {}
                ),
                Mapping,
            )
            else {}
        ),
    }


def normalize_learning_areas(
    learning_areas: Iterable[Mapping[str, Any]] | None,
) -> list[dict]:
    if learning_areas is None:
        return []

    if isinstance(
        learning_areas,
        Mapping,
    ):
        raise ValueError(
            "learning_areas must be an array."
        )

    result: list[dict] = []
    seen: set[str] = set()

    for item in learning_areas:
        normalized = normalize_learning_area(
            item
        )

        key = normalized[
            "learning_area_id"
        ]

        if key in seen:
            raise ValueError(
                f"Duplicate learning area: {key}"
            )

        seen.add(key)

        result.append(
            normalized
        )

    result.sort(
        key=lambda item: (
            item.get(
                "report_order",
                0,
            ),
            item.get(
                "name",
                "",
            ).lower(),
        )
    )

    return result


# =========================================================
# GRADE SCALE
# =========================================================

def normalize_grade_scale(
    values: Iterable[Mapping[str, Any]] | None,
) -> list[dict]:
    """
    Optional school-configured numeric grading scale.

    This is NOT mandatory for CBC reports because CBC performance
    levels/descriptors can exist without traditional letter grades.
    """

    if values is None:
        return []

    if isinstance(
        values,
        Mapping,
    ):
        raise ValueError(
            "grade_scale must be an array."
        )

    result: list[dict] = []

    for item in values:
        if not isinstance(
            item,
            Mapping,
        ):
            raise ValueError(
                "Each grade scale item must be an object."
            )

        min_percentage = _safe_float(
            item.get(
                "min_percentage"
            ),
            -1,
        )

        if not 0 <= min_percentage <= 100:
            raise ValueError(
                "grade scale min_percentage must be between 0 and 100."
            )

        grade = _text(
            item.get(
                "grade"
            )
        )

        if not grade:
            raise ValueError(
                "grade scale grade is required."
            )

        result.append(
            {
                "min_percentage": min_percentage,

                "grade": grade,

                "points": (
                    _safe_number(
                        item.get(
                            "points"
                        )
                    )
                    if item.get(
                        "points"
                    ) is not None
                    else None
                ),

                "remark": (
                    _text(
                        item.get(
                            "remark"
                        )
                    )
                    or None
                ),
            }
        )

    result.sort(
        key=lambda item: item[
            "min_percentage"
        ],
        reverse=True,
    )

    return result


# =========================================================
# PERFORMANCE SCALE
# =========================================================

def normalize_performance_scale(
    values: Iterable[Mapping[str, Any]] | None,
) -> list[dict]:
    """
    Normalize a school-specific or KNEC-aligned performance scale.

    Empty input keeps the system flexible.

    KJSEA-aligned schools can pass CBC_PERFORMANCE_LEVELS.
    """

    if values is None:
        return [
            dict(item)
            for item in CBC_PERFORMANCE_LEVELS
        ]

    if isinstance(
        values,
        Mapping,
    ):
        raise ValueError(
            "performance_scale must be an array."
        )

    result: list[dict] = []

    for item in values:
        if not isinstance(
            item,
            Mapping,
        ):
            raise ValueError(
                "Each performance scale item must be an object."
            )

        code = _text(
            item.get(
                "code"
            )
        )

        band = _text(
            item.get(
                "band"
            )
        )

        if not code:
            raise ValueError(
                "performance scale code is required."
            )

        if not band:
            raise ValueError(
                "performance scale band is required."
            )

        points = _safe_number(
            item.get(
                "points"
            )
        )

        result.append(
            {
                "code": code,
                "band": band,
                "points": points,
                "description": _text(
                    item.get(
                        "description"
                    )
                ),
            }
        )

    return result


# =========================================================
# SCHOOL CURRICULUM CONFIGURATION
# =========================================================

def curriculum_document(
    user_id: Any,
    school_id: Any,
    data: Mapping[str, Any],
) -> dict:
    """
    Create the school's curriculum configuration.

    The school defines which learning areas it offers for a particular
    level/grade/year/term.

    This configuration becomes the source of truth for internal
    report-card generation.
    """

    school = _id(
        school_id
    )

    creator = _id(
        user_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not creator:
        raise ValueError(
            "user_id is required."
        )

    if not isinstance(
        data,
        Mapping,
    ):
        raise ValueError(
            "Curriculum configuration must be an object."
        )

    education_level = (
        _text(
            data.get(
                "education_level",
                EDUCATION_PRIMARY,
            )
        ).lower()
        or EDUCATION_PRIMARY
    )

    if education_level not in EDUCATION_LEVELS:
        raise ValueError(
            "Invalid education level."
        )

    grade = _text(
        data.get(
            "grade"
        )
    )

    if not grade:
        raise ValueError(
            "grade is required."
        )

    framework = (
        _text(
            data.get(
                "assessment_framework",
                FRAMEWORK_CBC,
            )
        ).lower()
        or FRAMEWORK_CBC
    )

    if framework not in CURRICULUM_FRAMEWORKS:
        raise ValueError(
            "Invalid assessment framework."
        )

    pathway = (
        _text(
            data.get(
                "pathway"
            )
        ).lower()
        or None
    )

    if pathway and pathway not in SENIOR_SCHOOL_PATHWAYS:
        raise ValueError(
            "Invalid pathway."
        )

    learning_areas = normalize_learning_areas(
        data.get(
            "learning_areas",
            []
        )
    )

    if not learning_areas:
        raise ValueError(
            "At least one learning area must be configured."
        )

    academic_year = _text(
        data.get(
            "academic_year"
        )
    )

    term = _text(
        data.get(
            "term"
        )
    )

    report_settings = data.get(
        "report_settings",
        {},
    )

    if not isinstance(
        report_settings,
        Mapping,
    ):
        raise ValueError(
            "report_settings must be an object."
        )

    normalized_report_settings = {
        "report_type": (
            _text(
                report_settings.get(
                    "report_type",
                    REPORT_TYPE_SCHOOL,
                )
            ).lower()
            or REPORT_TYPE_SCHOOL
        ),

        "show_marks": _safe_bool(
            report_settings.get(
                "show_marks"
            ),
            True,
        ),

        "show_percentages": _safe_bool(
            report_settings.get(
                "show_percentages"
            ),
            True,
        ),

        "show_grades": _safe_bool(
            report_settings.get(
                "show_grades"
            ),
            False,
        ),

        "show_performance_levels": _safe_bool(
            report_settings.get(
                "show_performance_levels"
            ),
            True,
        ),

        "show_competencies": _safe_bool(
            report_settings.get(
                "show_competencies"
            ),
            True,
        ),

        "show_strands": _safe_bool(
            report_settings.get(
                "show_strands"
            ),
            False,
        ),

        "show_remarks": _safe_bool(
            report_settings.get(
                "show_remarks"
            ),
            True,
        ),

        "show_attendance": _safe_bool(
            report_settings.get(
                "show_attendance"
            ),
            True,
        ),

        "show_class_position": _safe_bool(
            report_settings.get(
                "show_class_position"
            ),
            False,
        ),

        "ranking_enabled": _safe_bool(
            report_settings.get(
                "ranking_enabled"
            ),
            False,
        ),

        "include_empty_learning_areas": _safe_bool(
            report_settings.get(
                "include_empty_learning_areas"
            ),
            False,
        ),

        "allow_numeric_scores": _safe_bool(
            report_settings.get(
                "allow_numeric_scores"
            ),
            True,
        ),

        "allow_letter_grades": _safe_bool(
            report_settings.get(
                "allow_letter_grades"
            ),
            False,
        ),

        "include_pathway_summary": _safe_bool(
            report_settings.get(
                "include_pathway_summary"
            ),
            education_level == EDUCATION_SENIOR_SCHOOL,
        ),

        "report_title": (
            _text(
                report_settings.get(
                    "report_title"
                )
            )
            or "Learner Progress Report"
        ),

        "custom_footer": _text(
            report_settings.get(
                "custom_footer"
            )
        ),

        "custom_header": _text(
            report_settings.get(
                "custom_header"
            )
        ),
    }

    report_type = normalized_report_settings[
        "report_type"
    ]

    if report_type not in REPORT_TYPES:
        raise ValueError(
            "Invalid report type."
        )

    curriculum_name = (
        _text(
            data.get(
                "name"
            )
        )
        or f"{grade} Curriculum"
    )

    status = (
        _text(
            data.get(
                "status",
                "active",
            )
        ).lower()
        or "active"
    )

    if status not in {
        "active",
        "draft",
        "archived",
    }:
        raise ValueError(
            "Invalid curriculum status."
        )

    now = now_utc()

    return {
        "schema_version": REPORT_SCHEMA_VERSION,

        "school_id": school,

        "name": curriculum_name,

        "education_level": education_level,

        "grade": grade,

        "pathway": pathway,

        "track": (
            _text(
                data.get(
                    "track"
                )
            )
            or None
        ),

        "assessment_framework": framework,

        "academic_year": academic_year,

        "term": term,

        # -------------------------------------------------
        # SCHOOL-SELECTED LEARNING AREAS
        # -------------------------------------------------

        "learning_areas": learning_areas,

        "learning_area_count": len(
            learning_areas
        ),

        "core_learning_area_ids": _string_list(
            data.get(
                "core_learning_area_ids"
            )
        ),

        "elective_learning_area_ids": _string_list(
            data.get(
                "elective_learning_area_ids"
            )
        ),

        # -------------------------------------------------
        # ASSESSMENT / REPORT CONFIGURATION
        # -------------------------------------------------

        "report_settings": normalized_report_settings,

        "grading_scale": normalize_grade_scale(
            data.get(
                "grading_scale"
            )
        ),

        "performance_scale": normalize_performance_scale(
            data.get(
                "performance_scale"
            )
        ),

        # -------------------------------------------------
        # CURRICULUM SOURCE
        # -------------------------------------------------

        "curriculum_source": {
            "authority": (
                _text(
                    data.get(
                        "curriculum_source",
                        "KICD",
                    )
                )
                or "KICD"
            ),
            "reference": _text(
                data.get(
                    "curriculum_reference"
                )
            ) or None,
            "verified_at": now,
        },

        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        "status": status,

        "created_by": creator,

        "created_at": now,

        "updated_at": now,

        "activated_at": (
            now
            if status == "active"
            else None
        ),
    }


# =========================================================
# EXAM / LEARNER REPORT DOCUMENT
# =========================================================

def exam_report_document(
    user_id: Any,
    school_id: Any,
    student: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    status: str = REPORT_GENERATED,
) -> dict:
    """
    Persist a generated learner report.

    CBC-first model:
        learning_areas
        performance levels
        competencies
        strand evidence
        descriptors
        optional numeric evidence

    Legacy:
        subjects
        subject_count
        overall_percentage
        overall_grade

    remain available for backward compatibility.
    """

    school = _id(
        school_id
    )

    creator = _id(
        user_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not creator:
        raise ValueError(
            "user_id is required."
        )

    normalized_status = (
        _text(status).lower()
        or REPORT_GENERATED
    )

    if normalized_status not in REPORT_STATUSES:
        raise ValueError(
            "Invalid exam report status."
        )

    if not isinstance(
        student,
        Mapping,
    ):
        raise ValueError(
            "student must be an object."
        )

    if not isinstance(
        report,
        Mapping,
    ):
        raise ValueError(
            "report must be an object."
        )

    snapshot = student_snapshot(
        student
    )

    # -----------------------------------------------------
    # CBC LEARNING AREAS
    # -----------------------------------------------------

    learning_areas = report.get(
        "learning_areas"
    )

    if learning_areas is None:
        # Backward compatibility with the original generator.
        learning_areas = report.get(
            "subjects",
            [],
        )

    if not isinstance(
        learning_areas,
        list,
    ):
        learning_areas = []

    normalized_learning_areas = []

    for item in learning_areas:
        if isinstance(
            item,
            Mapping,
        ):
            row = dict(item)

            # Preserve either naming convention.
            if not row.get(
                "learning_area"
            ):
                row["learning_area"] = _text(
                    row.get(
                        "subject"
                    )
                )

            if not row.get(
                "subject"
            ):
                row["subject"] = _text(
                    row.get(
                        "learning_area"
                    )
                )

            normalized_learning_areas.append(
                row
            )

    # -----------------------------------------------------
    # REPORT IDENTITY
    # -----------------------------------------------------

    assessment_framework = (
        _text(
            report.get(
                "assessment_framework",
                FRAMEWORK_CBC,
            )
        ).lower()
        or FRAMEWORK_CBC
    )

    if assessment_framework not in CURRICULUM_FRAMEWORKS:
        assessment_framework = FRAMEWORK_CBC

    report_type = (
        _text(
            report.get(
                "report_type",
                REPORT_TYPE_INDIVIDUAL_LEARNER,
            )
        ).lower()
        or REPORT_TYPE_INDIVIDUAL_LEARNER
    )

    if report_type not in REPORT_TYPES:
        report_type = REPORT_TYPE_INDIVIDUAL_LEARNER

    now = now_utc()

    subject_count = len(
        normalized_learning_areas
    )

    # -----------------------------------------------------
    # PERFORMANCE SUMMARY
    # -----------------------------------------------------

    numeric_summary = dict(
        report.get(
            "numeric_summary",
            {}
        )
        or {}
    )

    competency_summary = dict(
        report.get(
            "competency_summary",
            {}
        )
        or {}
    )

    pathway_summary = dict(
        report.get(
            "pathway_summary",
            {}
        )
        or {}
    )

    # -----------------------------------------------------
    # LEGACY NUMERIC FIELDS
    # -----------------------------------------------------

    total_score = _safe_number(
        report.get(
            "total_score"
        )
    )

    total_max_score = _safe_number(
        report.get(
            "total_max_score"
        )
    )

    overall_percentage = _safe_number(
        report.get(
            "overall_percentage"
        )
    )

    overall_grade = (
        _text(
            report.get(
                "overall_grade"
            )
        )
        or None
    )

    # -----------------------------------------------------
    # FINAL DOCUMENT
    # -----------------------------------------------------

    return {
        "schema_version": REPORT_SCHEMA_VERSION,

        "school_id": school,

        # -------------------------------------------------
        # LEARNER SNAPSHOT
        # -------------------------------------------------

        "student_id": snapshot[
            "student_id"
        ],

        "student_user_id": snapshot[
            "student_user_id"
        ],

        "student_name": snapshot[
            "student_name"
        ],

        "admission_number": snapshot[
            "admission_number"
        ],

        "student_code": snapshot[
            "student_code"
        ],

        "class_id": snapshot[
            "class_id"
        ],

        "class_name": snapshot[
            "class_name"
        ],

        "stream": snapshot[
            "stream"
        ],

        # -------------------------------------------------
        # CURRICULUM IDENTITY
        # -------------------------------------------------

        "education_level": (
            _text(
                report.get(
                    "education_level"
                )
            ).lower()
            or None
        ),

        "grade": _text(
            report.get(
                "grade"
            )
        ) or None,

        "pathway": (
            _text(
                report.get(
                    "pathway"
                )
            ).lower()
            or None
        ),

        "track": (
            _text(
                report.get(
                    "track"
                )
            )
            or None
        ),

        "assessment_framework": assessment_framework,

        "report_type": report_type,

        # -------------------------------------------------
        # EXAM IDENTITY
        # -------------------------------------------------

        "academic_year": _text(
            report.get(
                "academic_year"
            )
        ),

        "term": _text(
            report.get(
                "term"
            )
        ),

        "assessment_name": _text(
            report.get(
                "assessment_name"
            )
        ),

        "assessment_type": (
            _text(
                report.get(
                    "assessment_type",
                    "exam",
                )
            ).lower()
            or "exam"
        ),

        "assessment_date": (
            _text(
                report.get(
                    "assessment_date"
                )
            )
            or None
        ),

        # -------------------------------------------------
        # CBC REPORT CONTENT
        # -------------------------------------------------

        "learning_areas": normalized_learning_areas,

        # Compatibility alias for older frontend/report code.
        "subjects": normalized_learning_areas,

        "learning_area_count": subject_count,

        "subject_count": subject_count,

        "numeric_summary": numeric_summary,

        "competency_summary": competency_summary,

        "pathway_summary": pathway_summary,

        "performance_levels": list(
            report.get(
                "performance_levels",
                []
            )
            or []
        ),

        "competencies": list(
            report.get(
                "competencies",
                []
            )
            or []
        ),

        "strand_summary": list(
            report.get(
                "strand_summary",
                []
            )
            or []
        ),

        # -------------------------------------------------
        # OPTIONAL NUMERIC SUMMARY
        # -------------------------------------------------

        "total_score": total_score,

        "total_max_score": total_max_score,

        "overall_percentage": overall_percentage,

        "overall_grade": overall_grade,

        "overall_points": _safe_number(
            report.get(
                "overall_points"
            )
        ),

        "overall_performance_level": (
            _text(
                report.get(
                    "overall_performance_level"
                )
            )
            or None
        ),

        "overall_competency": (
            _text(
                report.get(
                    "overall_competency"
                )
            )
            or None
        ),

        # -------------------------------------------------
        # POSITION
        # -------------------------------------------------
        #
        # Optional only. CBC/KJSEA reporting should not depend
        # on traditional ranking.
        #
        "class_position": _safe_number(
            report.get(
                "class_position"
            )
        ),

        "class_size": _safe_number(
            report.get(
                "class_size"
            )
        ),

        "ranking_enabled": _safe_bool(
            report.get(
                "ranking_enabled"
            ),
            False,
        ),

        # -------------------------------------------------
        # ATTENDANCE
        # -------------------------------------------------

        "attendance": dict(
            report.get(
                "attendance",
                {}
            )
            or {}
        ),

        # -------------------------------------------------
        # REMARKS
        # -------------------------------------------------

        "teacher_remarks": _text(
            report.get(
                "teacher_remarks"
            )
        ),

        "principal_remarks": _text(
            report.get(
                "principal_remarks"
            )
        ),

        "learner_remarks": _text(
            report.get(
                "learner_remarks"
            )
        ),

        "next_steps": _string_list(
            report.get(
                "next_steps"
            )
        ),

        "strengths": _string_list(
            report.get(
                "strengths"
            )
        ),

        "areas_for_improvement": _string_list(
            report.get(
                "areas_for_improvement"
            )
        ),

        # -------------------------------------------------
        # BRANDING / PRINT
        # -------------------------------------------------

        "report_branding": dict(
            report.get(
                "report_branding",
                {}
            )
            or {}
        ),

        "print": dict(
            report.get(
                "print",
                {}
            )
            or {}
        ),

        # -------------------------------------------------
        # GENERATION
        # -------------------------------------------------

        "generation": {
            "engine": (
                _text(
                    report.get(
                        "generation_engine"
                    )
                )
                or "deterministic"
            ),

            "version": (
                _text(
                    report.get(
                        "generation_version"
                    )
                )
                or REPORT_SCHEMA_VERSION
            ),

            "generated_at": now,

            "generated_by": creator,
        },

        # -------------------------------------------------
        # STATUS / AUDIT
        # -------------------------------------------------

        "status": normalized_status,

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# PROGRAMME ACTIVITY
# =========================================================

def programme_activity(
    activity: Mapping[str, Any],
) -> dict:
    """
    Normalize one post-examination school programme activity.
    """

    if not isinstance(
        activity,
        Mapping,
    ):
        raise ValueError(
            "Each programme activity must be an object."
        )

    title = _text(
        activity.get(
            "title"
        )
    )

    if not title:
        raise ValueError(
            "Programme activity title is required."
        )

    activity_type = (
        _text(
            activity.get(
                "activity_type",
                "other",
            )
        ).lower()
        or "other"
    )

    if activity_type not in ACTIVITY_TYPES:
        raise ValueError(
            f"Invalid programme activity type: {activity_type}"
        )

    return {
        "activity_id": (
            _id(
                activity.get(
                    "activity_id"
                )
            )
            or None
        ),

        "title": title,

        "activity_type": activity_type,

        "description": _text(
            activity.get(
                "description"
            )
        ),

        "date": _text(
            activity.get(
                "date"
            )
        ),

        "day": (
            _text(
                activity.get(
                    "day"
                )
            ).lower()
            or None
        ),

        "start_time": (
            _text(
                activity.get(
                    "start_time"
                )
            )
            or None
        ),

        "end_time": (
            _text(
                activity.get(
                    "end_time"
                )
            )
            or None
        ),

        "audience": _string_list(
            activity.get(
                "audience"
            )
        ),

        "class_names": _string_list(
            activity.get(
                "class_names"
            )
        ),

        "facilitator": (
            _text(
                activity.get(
                    "facilitator"
                )
            )
            or None
        ),

        "venue": (
            _text(
                activity.get(
                    "venue"
                )
            )
            or None
        ),

        "notes": _text(
            activity.get(
                "notes"
            )
        ),
    }


# =========================================================
# PROGRAMME DOCUMENT
# =========================================================

def programme_document(
    user_id: Any,
    school_id: Any,
    programme: Mapping[str, Any],
    *,
    status: str = PROGRAMME_GENERATED,
) -> dict:
    """
    Build a persisted post-examination school programme.
    """

    school = _id(
        school_id
    )

    creator = _id(
        user_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not creator:
        raise ValueError(
            "user_id is required."
        )

    if not isinstance(
        programme,
        Mapping,
    ):
        raise ValueError(
            "programme must be an object."
        )

    normalized_status = (
        _text(status).lower()
        or PROGRAMME_GENERATED
    )

    if normalized_status not in PROGRAMME_STATUSES:
        raise ValueError(
            "Invalid programme status."
        )

    activities = [
        programme_activity(
            activity
        )
        for activity in programme.get(
            "activities",
            []
        )
        if isinstance(
            activity,
            Mapping,
        )
    ]

    now = now_utc()

    return {
        "schema_version": REPORT_SCHEMA_VERSION,

        "school_id": school,

        "title": (
            _text(
                programme.get(
                    "title"
                )
            )
            or "Post-Examination School Programme"
        ),

        "description": _text(
            programme.get(
                "description"
            )
        ),

        "academic_year": _text(
            programme.get(
                "academic_year"
            )
        ),

        "term": _text(
            programme.get(
                "term"
            )
        ),

        "programme_type": (
            _text(
                programme.get(
                    "programme_type",
                    "post_exam",
                )
            ).lower()
            or "post_exam"
        ),

        "start_date": (
            _text(
                programme.get(
                    "start_date"
                )
            )
            or None
        ),

        "end_date": (
            _text(
                programme.get(
                    "end_date"
                )
            )
            or None
        ),

        "activities": activities,

        "activity_count": len(
            activities
        ),

        "target_classes": _string_list(
            programme.get(
                "target_classes"
            )
        ),

        "target_students": _string_list(
            programme.get(
                "target_students"
            )
        ),

        "generation": {
            "engine": (
                _text(
                    programme.get(
                        "generation_engine"
                    )
                )
                or "deterministic"
            ),

            "version": (
                _text(
                    programme.get(
                        "generation_version"
                    )
                )
                or REPORT_SCHEMA_VERSION
            ),

            "generated_at": now,

            "generated_by": creator,
        },

        "status": normalized_status,

        "created_by": creator,

        "created_at": now,

        "updated_at": now,

        "published_at": None,

        "published_by": None,
    }


# =========================================================
# PUBLICATION HELPERS
# =========================================================

def published_report_fields(
    user_id: Any,
) -> dict:
    user = _id(
        user_id
    )

    if not user:
        raise ValueError(
            "Publishing user is required."
        )

    now = now_utc()

    return {
        "status": REPORT_PUBLISHED,
        "published_at": now,
        "published_by": user,
        "updated_at": now,
    }


def published_programme_fields(
    user_id: Any,
) -> dict:
    user = _id(
        user_id
    )

    if not user:
        raise ValueError(
            "Publishing user is required."
        )

    now = now_utc()

    return {
        "status": PROGRAMME_PUBLISHED,
        "published_at": now,
        "published_by": user,
        "updated_at": now,
    }


# =========================================================
# ARCHIVE HELPERS
# =========================================================

def archived_report_fields() -> dict:
    return {
        "status": REPORT_ARCHIVED,
        "updated_at": now_utc(),
    }


def archived_programme_fields() -> dict:
    return {
        "status": PROGRAMME_ARCHIVED,
        "updated_at": now_utc(),
    }