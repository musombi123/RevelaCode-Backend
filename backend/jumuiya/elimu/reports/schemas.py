# backend/jumuiya/elimu/reports/schemas.py

from __future__ import annotations

from typing import Any


# =========================================================
# CONSTANTS
# =========================================================

EDUCATION_LEVELS = {
    "pre_primary",
    "primary",
    "junior_school",
    "senior_school",
    "sne",
}

CURRICULUM_FRAMEWORKS = {
    "cbc",
    "school_internal",
    "hybrid",
}

SENIOR_SCHOOL_PATHWAYS = {
    "stem",
    "social_sciences",
    "arts_and_sports_science",
}

LEARNING_AREA_CATEGORIES = {
    "core",
    "elective",
    "compulsory",
    "optional",
    "enrichment",
    "pathway",
    "other",
}

REPORT_TYPES = {
    "school_report",
    "individual_learner_report",
    "kjsea_aligned",
    "progress_report",
}

REPORT_FORMATS = {
    "json",
    "print",
    "pdf",
}

PROGRAMME_ACTIVITY_TYPES = {
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
}


# =========================================================
# BASIC HELPERS
# =========================================================

def _object(
    data: Any,
) -> dict:
    if not isinstance(data, dict):
        raise ValueError(
            "JSON object required."
        )

    return data


def _text(
    data: dict,
    key: str,
    required: bool = False,
    max_len: int = 500,
) -> str:
    value = data.get(
        key,
        "",
    )

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip()

    if required and not value:
        raise ValueError(
            f"{key} is required."
        )

    if len(value) > max_len:
        raise ValueError(
            f"{key} must not exceed {max_len} characters."
        )

    return value


def _choice(
    data: dict,
    key: str,
    choices: set[str],
    default: str | None = None,
) -> str | None:
    value = data.get(
        key,
        default,
    )

    if value is None:
        return default

    if not isinstance(value, str):
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip().lower()

    if value not in choices:
        raise ValueError(
            f"{key} is invalid."
        )

    return value


def _number(
    data: dict,
    key: str,
    required: bool = False,
    minimum: float = 0,
    maximum: float | None = None,
) -> int | float | None:
    value = data.get(key)

    if value is None:
        if required:
            raise ValueError(
                f"{key} is required."
            )

        return None

    if isinstance(value, bool):
        raise ValueError(
            f"{key} must be a number."
        )

    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            f"{key} must be a number."
        )

    if number < minimum:
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    if maximum is not None and number > maximum:
        raise ValueError(
            f"{key} must not exceed {maximum}."
        )

    if number.is_integer():
        return int(number)

    return number


def _integer(
    data: dict,
    key: str,
    required: bool = False,
    minimum: int = 0,
    maximum: int | None = None,
) -> int | None:
    value = _number(
        data,
        key,
        required=required,
        minimum=minimum,
        maximum=maximum,
    )

    if value is None:
        return None

    if not float(value).is_integer():
        raise ValueError(
            f"{key} must be a whole number."
        )

    return int(value)


def _bool(
    data: dict,
    key: str,
    default: bool = False,
) -> bool:
    value = data.get(
        key,
        default,
    )

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

    raise ValueError(
        f"{key} must be boolean."
    )


def _list(
    data: dict,
    key: str,
    max_items: int = 100,
    item_max_len: int = 200,
) -> list[str]:
    value = data.get(
        key,
        [],
    )

    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, list):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > max_items:
        raise ValueError(
            f"{key} cannot contain more than {max_items} items."
        )

    result: list[str] = []

    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"Each {key} item must be text."
            )

        item = item.strip()

        if not item:
            continue

        if len(item) > item_max_len:
            raise ValueError(
                f"{key} items must not exceed {item_max_len} characters."
            )

        if item not in result:
            result.append(item)

    return result


def _object_list(
    data: dict,
    key: str,
    max_items: int = 100,
) -> list[dict]:
    value = data.get(
        key,
        [],
    )

    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > max_items:
        raise ValueError(
            f"{key} cannot contain more than {max_items} items."
        )

    result: list[dict] = []

    for item in value:
        if not isinstance(item, dict):
            raise ValueError(
                f"Each {key} item must be an object."
            )

        result.append(item)

    return result


def _dict(
    data: dict,
    key: str,
    max_keys: int = 30,
) -> dict:
    value = data.get(
        key,
        {},
    )

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(
            f"{key} must be an object."
        )

    if len(value) > max_keys:
        raise ValueError(
            f"{key} contains too many fields."
        )

    return value


# =========================================================
# DATE / TIME
# =========================================================

def _date_text(
    data: dict,
    key: str,
    required: bool = False,
) -> str:
    value = _text(
        data,
        key,
        required,
        30,
    )

    if not value:
        return ""

    # Expected canonical format: YYYY-MM-DD
    parts = value.split("-")

    if len(parts) != 3:
        raise ValueError(
            f"{key} must use YYYY-MM-DD format."
        )

    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
    except ValueError:
        raise ValueError(
            f"{key} must use YYYY-MM-DD format."
        )

    if not (
        1 <= month <= 12
        and 1 <= day <= 31
        and year >= 2000
    ):
        raise ValueError(
            f"{key} must use YYYY-MM-DD format."
        )

    return value


def _time_text(
    data: dict,
    key: str,
    required: bool = False,
) -> str:
    value = _text(
        data,
        key,
        required,
        10,
    )

    if not value:
        return ""

    parts = value.split(":")

    if len(parts) != 2:
        raise ValueError(
            f"{key} must use HH:MM format."
        )

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        raise ValueError(
            f"{key} must use HH:MM format."
        )

    if not (
        0 <= hours <= 23
        and 0 <= minutes <= 59
    ):
        raise ValueError(
            f"{key} must use HH:MM format."
        )

    return f"{hours:02d}:{minutes:02d}"


# =========================================================
# PERFORMANCE SCALE
# =========================================================

def _performance_scale(
    data: dict,
    key: str = "performance_scale",
) -> list[dict]:
    items = _object_list(
        data,
        key,
        max_items=30,
    )

    result = []

    for index, item in enumerate(items):
        code = _text(
            item,
            "code",
            True,
            30,
        ).upper()

        band = _text(
            item,
            "band",
            True,
            100,
        )

        points = _number(
            item,
            "points",
            False,
            minimum=0,
            maximum=100,
        )

        description = _text(
            item,
            "description",
            False,
            500,
        )

        result.append(
            {
                "code": code,
                "band": band,
                "points": points,
                "description": description,
            }
        )

    return result


# =========================================================
# GRADE SCALE
# =========================================================

def _grade_scale(
    data: dict,
    key: str = "grading_scale",
) -> list[dict]:
    items = _object_list(
        data,
        key,
        max_items=30,
    )

    result = []

    for item in items:
        minimum = _number(
            item,
            "min_percentage",
            True,
            minimum=0,
            maximum=100,
        )

        grade = _text(
            item,
            "grade",
            True,
            30,
        )

        points = _number(
            item,
            "points",
            False,
            minimum=0,
            maximum=1000,
        )

        remark = _text(
            item,
            "remark",
            False,
            300,
        )

        result.append(
            {
                "min_percentage": minimum,
                "grade": grade,
                "points": points,
                "remark": remark,
            }
        )

    return result


# =========================================================
# LEARNING AREA
# =========================================================

def learning_area_payload(
    data: dict,
) -> dict:
    """
    Validate one learning-area configuration.

    The school can configure its own offered learning areas, while
    retaining CBC metadata such as category, pathway, track,
    competencies and strands.
    """

    _object(data)

    learning_area_id = _text(
        data,
        "learning_area_id",
        False,
        120,
    )

    name = _text(
        data,
        "name",
        True,
        200,
    )

    if not learning_area_id:
        # The model layer can derive a stable fallback from the name.
        learning_area_id = (
            name.lower()
            .replace(
                " ",
                "_",
            )
        )

    code = _text(
        data,
        "code",
        False,
        40,
    )

    short_name = _text(
        data,
        "short_name",
        False,
        100,
    )

    category = _choice(
        data,
        "category",
        LEARNING_AREA_CATEGORIES,
        "other",
    )

    pathway = data.get(
        "pathway"
    )

    if pathway is not None and not isinstance(
        pathway,
        str,
    ):
        raise ValueError(
            "pathway must be text."
        )

    pathway = (
        pathway.strip().lower()
        if isinstance(
            pathway,
            str,
        )
        else None
    )

    if pathway and pathway not in SENIOR_SCHOOL_PATHWAYS:
        raise ValueError(
            "Invalid learning area pathway."
        )

    track = _text(
        data,
        "track",
        False,
        100,
    )

    core_group = _text(
        data,
        "core_group",
        False,
        100,
    ).lower()

    assessment_model = _text(
        data,
        "assessment_model",
        False,
        60,
    ).lower() or "cbc"

    grading_model = _text(
        data,
        "grading_model",
        False,
        60,
    ).lower() or "performance_level"

    weekly_lessons = _integer(
        data,
        "weekly_lessons",
        False,
        minimum=0,
        maximum=100,
    )

    strands = _object_list(
        data,
        "strands",
        max_items=100,
    )

    normalized_strands = []

    for strand in strands:
        strand_id = _text(
            strand,
            "id",
            False,
            100,
        )

        strand_name = _text(
            strand,
            "name",
            True,
            200,
        )

        sub_strands = _list(
            strand,
            "sub_strands",
            max_items=100,
            item_max_len=200,
        )

        normalized_strands.append(
            {
                "id": strand_id or None,
                "name": strand_name,
                "sub_strands": sub_strands,
            }
        )

    competencies = _list(
        data,
        "competencies",
        max_items=100,
        item_max_len=300,
    )

    metadata = _dict(
        data,
        "metadata",
        max_keys=30,
    )

    return {
        "learning_area_id": learning_area_id,

        "code": code or None,

        "name": name,

        "short_name": short_name or None,

        "category": category,

        "required": _bool(
            data,
            "required",
            False,
        ),

        "selected": _bool(
            data,
            "selected",
            False,
        ),

        "assessment_enabled": _bool(
            data,
            "assessment_enabled",
            True,
        ),

        "include_in_report": _bool(
            data,
            "include_in_report",
            True,
        ),

        "report_order": _integer(
            data,
            "report_order",
            False,
            minimum=0,
            maximum=1000,
        ) or 0,

        "weekly_lessons": weekly_lessons,

        "pathway": pathway,

        "track": track or None,

        "core_group": core_group or None,

        "strands": normalized_strands,

        "competencies": competencies,

        "assessment_model": assessment_model,

        "grading_model": grading_model,

        "metadata": metadata,
    }


# =========================================================
# SCHOOL CURRICULUM PAYLOAD
# =========================================================

def curriculum_payload(
    data: dict,
) -> dict:
    """
    Configure the learning areas offered by a school for one
    education level / grade / pathway / academic period.
    """

    _object(data)

    education_level = _choice(
        data,
        "education_level",
        EDUCATION_LEVELS,
        "primary",
    )

    grade = _text(
        data,
        "grade",
        True,
        100,
    )

    framework = _choice(
        data,
        "assessment_framework",
        CURRICULUM_FRAMEWORKS,
        "cbc",
    )

    pathway = data.get(
        "pathway"
    )

    if pathway is not None:
        if not isinstance(
            pathway,
            str,
        ):
            raise ValueError(
                "pathway must be text."
            )

        pathway = pathway.strip().lower()

        if pathway not in SENIOR_SCHOOL_PATHWAYS:
            raise ValueError(
                "Invalid pathway."
            )

    track = _text(
        data,
        "track",
        False,
        100,
    )

    academic_year = _text(
        data,
        "academic_year",
        False,
        30,
    )

    term = _text(
        data,
        "term",
        False,
        50,
    )

    name = _text(
        data,
        "name",
        False,
        200,
    )

    learning_area_items = _object_list(
        data,
        "learning_areas",
        max_items=100,
    )

    if not learning_area_items:
        raise ValueError(
            "At least one learning area must be configured."
        )

    learning_areas = [
        learning_area_payload(
            item
        )
        for item in learning_area_items
    ]

    ids = [
        item[
            "learning_area_id"
        ]
        for item in learning_areas
    ]

    if len(ids) != len(set(ids)):
        raise ValueError(
            "Duplicate learning areas are not allowed."
        )

    core_ids = _list(
        data,
        "core_learning_area_ids",
        max_items=100,
        item_max_len=120,
    )

    elective_ids = _list(
        data,
        "elective_learning_area_ids",
        max_items=100,
        item_max_len=120,
    )

    known_ids = set(ids)

    unknown_core = [
        value
        for value in core_ids
        if value not in known_ids
    ]

    unknown_electives = [
        value
        for value in elective_ids
        if value not in known_ids
    ]

    if unknown_core:
        raise ValueError(
            "core_learning_area_ids contains an unknown learning area."
        )

    if unknown_electives:
        raise ValueError(
            "elective_learning_area_ids contains an unknown learning area."
        )

    report_settings = _dict(
        data,
        "report_settings",
        max_keys=40,
    )

    report_type = _choice(
        report_settings,
        "report_type",
        REPORT_TYPES,
        "school_report",
    )

    normalized_report_settings = {
        "report_type": report_type,

        "show_marks": _bool(
            report_settings,
            "show_marks",
            True,
        ),

        "show_percentages": _bool(
            report_settings,
            "show_percentages",
            True,
        ),

        "show_grades": _bool(
            report_settings,
            "show_grades",
            False,
        ),

        "show_performance_levels": _bool(
            report_settings,
            "show_performance_levels",
            True,
        ),

        "show_competencies": _bool(
            report_settings,
            "show_competencies",
            True,
        ),

        "show_strands": _bool(
            report_settings,
            "show_strands",
            False,
        ),

        "show_remarks": _bool(
            report_settings,
            "show_remarks",
            True,
        ),

        "show_attendance": _bool(
            report_settings,
            "show_attendance",
            True,
        ),

        "show_class_position": _bool(
            report_settings,
            "show_class_position",
            False,
        ),

        "ranking_enabled": _bool(
            report_settings,
            "ranking_enabled",
            False,
        ),

        "include_empty_learning_areas": _bool(
            report_settings,
            "include_empty_learning_areas",
            False,
        ),

        "allow_numeric_scores": _bool(
            report_settings,
            "allow_numeric_scores",
            True,
        ),

        "allow_letter_grades": _bool(
            report_settings,
            "allow_letter_grades",
            False,
        ),

        "include_pathway_summary": _bool(
            report_settings,
            "include_pathway_summary",
            education_level == "senior_school",
        ),

        "report_title": (
            _text(
                report_settings,
                "report_title",
                False,
                200,
            )
            or "Learner Progress Report"
        ),

        "custom_header": _text(
            report_settings,
            "custom_header",
            False,
            500,
        ),

        "custom_footer": _text(
            report_settings,
            "custom_footer",
            False,
            500,
        ),
    }

    # Numeric ranking is deliberately disabled by default.
    if not normalized_report_settings[
        "ranking_enabled"
    ]:
        normalized_report_settings[
            "show_class_position"
        ] = False

    grading_scale = _grade_scale(
        data,
        "grading_scale",
    )

    performance_scale = _performance_scale(
        data,
        "performance_scale",
    )

    return {
        "name": (
            name
            or f"{grade} Curriculum"
        ),

        "education_level": education_level,

        "grade": grade,

        "pathway": pathway,

        "track": track or None,

        "assessment_framework": framework,

        "academic_year": academic_year,

        "term": term,

        "learning_areas": learning_areas,

        "core_learning_area_ids": core_ids,

        "elective_learning_area_ids": elective_ids,

        "report_settings": normalized_report_settings,

        "grading_scale": grading_scale,

        "performance_scale": performance_scale,

        "curriculum_reference": _text(
            data,
            "curriculum_reference",
            False,
            300,
        ),

        "curriculum_source": _text(
            data,
            "curriculum_source",
            False,
            200,
        ) or "KICD",

        "status": _choice(
            data,
            "status",
            {
                "draft",
                "active",
                "archived",
            },
            "active",
        ),
    }


# =========================================================
# EXAM REPORT PAYLOAD
# =========================================================

def exam_report_payload(
    data: dict,
) -> dict:
    """
    Generate one learner's report from the school's configured
    learning areas and stored assessment evidence.
    """

    _object(data)

    student_id = _text(
        data,
        "student_id",
        True,
        120,
    )

    academic_year = _text(
        data,
        "academic_year",
        False,
        30,
    )

    term = _text(
        data,
        "term",
        False,
        50,
    )

    assessment_name = _text(
        data,
        "assessment_name",
        False,
        200,
    )

    assessment_type = _text(
        data,
        "assessment_type",
        False,
        60,
    ).lower() or "exam"

    if not assessment_type:
        assessment_type = "exam"

    include_attendance = _bool(
        data,
        "include_attendance",
        True,
    )

    include_empty = _bool(
        data,
        "include_empty_learning_areas",
        False,
    )

    ranking_enabled = _bool(
        data,
        "ranking_enabled",
        False,
    )

    class_position = _integer(
        data,
        "class_position",
        False,
        minimum=1,
        maximum=100000,
    )

    class_size = _integer(
        data,
        "class_size",
        False,
        minimum=1,
        maximum=100000,
    )

    if not ranking_enabled:
        class_position = None
        class_size = None

    report_type = _choice(
        data,
        "report_type",
        REPORT_TYPES,
        "individual_learner_report",
    )

    report_format = _choice(
        data,
        "format",
        REPORT_FORMATS,
        "json",
    )

    teacher_remarks = _text(
        data,
        "teacher_remarks",
        False,
        2000,
    )

    principal_remarks = _text(
        data,
        "principal_remarks",
        False,
        2000,
    )

    learner_remarks = _text(
        data,
        "learner_remarks",
        False,
        1000,
    )

    strengths = _list(
        data,
        "strengths",
        max_items=30,
        item_max_len=500,
    )

    areas_for_improvement = _list(
        data,
        "areas_for_improvement",
        max_items=30,
        item_max_len=500,
    )

    next_steps = _list(
        data,
        "next_steps",
        max_items=30,
        item_max_len=500,
    )

    report_branding = _dict(
        data,
        "report_branding",
        max_keys=30,
    )

    print_options = _dict(
        data,
        "print",
        max_keys=30,
    )

    return {
        "student_id": student_id,

        "academic_year": academic_year,

        "term": term,

        "assessment_name": assessment_name,

        "assessment_type": assessment_type,

        "report_type": report_type,

        "format": report_format,

        "include_attendance": include_attendance,

        "include_empty_learning_areas": include_empty,

        "ranking_enabled": ranking_enabled,

        "class_position": class_position,

        "class_size": class_size,

        "teacher_remarks": teacher_remarks,

        "principal_remarks": principal_remarks,

        "learner_remarks": learner_remarks,

        "strengths": strengths,

        "areas_for_improvement": areas_for_improvement,

        "next_steps": next_steps,

        "grading_scale": _grade_scale(
            data,
            "grading_scale",
        ),

        "performance_scale": _performance_scale(
            data,
            "performance_scale",
        ),

        "report_branding": report_branding,

        "print": print_options,
    }


# =========================================================
# BATCH EXAM REPORTS
# =========================================================

def batch_exam_reports_payload(
    data: dict,
) -> dict:
    """
    Generate reports for a whole class or an explicit student list.
    """

    _object(data)

    student_ids = _list(
        data,
        "student_ids",
        max_items=5000,
        item_max_len=120,
    )

    class_name = _text(
        data,
        "class_name",
        False,
        100,
    )

    if not student_ids and not class_name:
        raise ValueError(
            "Provide either student_ids or class_name."
        )

    academic_year = _text(
        data,
        "academic_year",
        False,
        30,
    )

    term = _text(
        data,
        "term",
        False,
        50,
    )

    assessment_name = _text(
        data,
        "assessment_name",
        False,
        200,
    )

    assessment_type = _text(
        data,
        "assessment_type",
        False,
        60,
    ).lower() or "exam"

    report_type = _choice(
        data,
        "report_type",
        REPORT_TYPES,
        "individual_learner_report",
    )

    ranking_enabled = _bool(
        data,
        "ranking_enabled",
        False,
    )

    include_attendance = _bool(
        data,
        "include_attendance",
        True,
    )

    report_branding = _dict(
        data,
        "report_branding",
        max_keys=30,
    )

    return {
        "student_ids": student_ids,

        "class_name": class_name,

        "academic_year": academic_year,

        "term": term,

        "assessment_name": assessment_name,

        "assessment_type": assessment_type,

        "report_type": report_type,

        "ranking_enabled": ranking_enabled,

        "include_attendance": include_attendance,

        "grading_scale": _grade_scale(
            data,
            "grading_scale",
        ),

        "performance_scale": _performance_scale(
            data,
            "performance_scale",
        ),

        "teacher_remarks": _text(
            data,
            "teacher_remarks",
            False,
            2000,
        ),

        "principal_remarks": _text(
            data,
            "principal_remarks",
            False,
            2000,
        ),

        "report_branding": report_branding,
    }


# =========================================================
# REPORT PUBLISH
# =========================================================

def publish_report_payload(
    data: dict,
) -> dict:
    _object(data)

    return {
        "report_id": _text(
            data,
            "report_id",
            True,
            120,
        ),
    }


# =========================================================
# PROGRAMME ACTIVITY
# =========================================================

def programme_activity_payload(
    data: dict,
) -> dict:
    _object(data)

    activity_type = _choice(
        data,
        "activity_type",
        PROGRAMME_ACTIVITY_TYPES,
        "other",
    )

    title = _text(
        data,
        "title",
        True,
        200,
    )

    date_value = _date_text(
        data,
        "date",
        False,
    )

    start_time = _time_text(
        data,
        "start_time",
        False,
    )

    end_time = _time_text(
        data,
        "end_time",
        False,
    )

    if start_time and end_time:
        if start_time >= end_time:
            raise ValueError(
                "end_time must be after start_time."
            )

    return {
        "activity_id": (
            _text(
                data,
                "activity_id",
                False,
                120,
            )
            or None
        ),

        "title": title,

        "activity_type": activity_type,

        "description": _text(
            data,
            "description",
            False,
            3000,
        ),

        "date": date_value,

        "day": _text(
            data,
            "day",
            False,
            20,
        ).lower() or None,

        "start_time": start_time or None,

        "end_time": end_time or None,

        "audience": _list(
            data,
            "audience",
            max_items=50,
            item_max_len=100,
        ),

        "class_names": _list(
            data,
            "class_names",
            max_items=200,
            item_max_len=100,
        ),

        "facilitator": _text(
            data,
            "facilitator",
            False,
            200,
        ) or None,

        "venue": _text(
            data,
            "venue",
            False,
            200,
        ) or None,

        "notes": _text(
            data,
            "notes",
            False,
            1500,
        ),
    }


# =========================================================
# POST-EXAM PROGRAMME PAYLOAD
# =========================================================

def programme_payload(
    data: dict,
) -> dict:
    """
    Create the request contract for generating a post-exam
    school programme.
    """

    _object(data)

    start_date = _date_text(
        data,
        "start_date",
        True,
    )

    end_date = _date_text(
        data,
        "end_date",
        True,
    )

    if end_date < start_date:
        raise ValueError(
            "end_date cannot be before start_date."
        )

    activities = [
        programme_activity_payload(
            item
        )
        for item in _object_list(
            data,
            "activities",
            max_items=500,
        )
    ]

    if not activities:
        raise ValueError(
            "At least one programme activity is required."
        )

    return {
        "title": (
            _text(
                data,
                "title",
                False,
                200,
            )
            or "Post-Examination School Programme"
        ),

        "description": _text(
            data,
            "description",
            False,
            3000,
        ),

        "academic_year": _text(
            data,
            "academic_year",
            False,
            30,
        ),

        "term": _text(
            data,
            "term",
            False,
            50,
        ),

        "programme_type": (
            _text(
                data,
                "programme_type",
                False,
                80,
            ).lower()
            or "post_exam"
        ),

        "start_date": start_date,

        "end_date": end_date,

        "daily_start_time": (
            _time_text(
                data,
                "daily_start_time",
                False,
            )
            or "08:00"
        ),

        "daily_end_time": (
            _time_text(
                data,
                "daily_end_time",
                False,
            )
            or "16:00"
        ),

        "activities": activities,

        "school_days": _integer(
            data,
            "school_days",
            False,
            minimum=1,
            maximum=366,
        ),

        "avoid_weekends": _bool(
            data,
            "avoid_weekends",
            True,
        ),

        "report_based": _bool(
            data,
            "report_based",
            False,
        ),

        "target_classes": _list(
            data,
            "target_classes",
            max_items=200,
            item_max_len=100,
        ),

        "target_students": _list(
            data,
            "target_students",
            max_items=5000,
            item_max_len=120,
        ),
    }


# =========================================================
# PROGRAMME UPDATE
# =========================================================

def programme_update_payload(
    data: dict,
) -> dict:
    _object(data)

    activities = [
        programme_activity_payload(
            item
        )
        for item in _object_list(
            data,
            "activities",
            max_items=500,
        )
    ]

    result = {}

    if "title" in data:
        result["title"] = _text(
            data,
            "title",
            True,
            200,
        )

    if "description" in data:
        result["description"] = _text(
            data,
            "description",
            False,
            3000,
        )

    if "start_date" in data:
        result["start_date"] = _date_text(
            data,
            "start_date",
            True,
        )

    if "end_date" in data:
        result["end_date"] = _date_text(
            data,
            "end_date",
            True,
        )

    if "daily_start_time" in data:
        result["daily_start_time"] = _time_text(
            data,
            "daily_start_time",
            False,
        )

    if "daily_end_time" in data:
        result["daily_end_time"] = _time_text(
            data,
            "daily_end_time",
            False,
        )

    if "activities" in data:
        result["activities"] = activities

    if "target_classes" in data:
        result["target_classes"] = _list(
            data,
            "target_classes",
            max_items=200,
            item_max_len=100,
        )

    if "target_students" in data:
        result["target_students"] = _list(
            data,
            "target_students",
            max_items=5000,
            item_max_len=120,
        )

    if not result:
        raise ValueError(
            "At least one programme field must be supplied."
        )

    return result