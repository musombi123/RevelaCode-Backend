# backend/jumuiya/elimu/reports/generator.py

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


# =========================================================
# GENERATOR VERSION
# =========================================================

GENERATOR_VERSION = "2.0"


# =========================================================
# ERRORS
# =========================================================

class ReportGenerationError(ValueError):
    """
    Controlled error raised when a report or school programme
    cannot be generated safely.
    """


# =========================================================
# BASIC HELPERS
# =========================================================

def _text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _lower(
    value: Any,
) -> str:
    return _text(value).lower()


def _safe_decimal(
    value: Any,
    default: Decimal = Decimal("0"),
) -> Decimal:
    if value is None:
        return default

    if isinstance(value, Decimal):
        return value

    if isinstance(value, bool):
        return default

    try:
        return Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return default


def _safe_number(
    value: Any,
    default: int | float | None = None,
) -> int | float | None:
    if value is None:
        return default

    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default

    if number.is_integer():
        return int(number)

    return number


def _round_decimal(
    value: Decimal,
    places: int = 2,
) -> Decimal:
    quantizer = Decimal(
        "1."
        + (
            "0" * places
        )
    )

    return value.quantize(
        quantizer
    )


def _json_number(
    value: Decimal,
) -> int | float:
    value = _round_decimal(
        value
    )

    if value == value.to_integral_value():
        return int(value)

    return float(value)


def _percentage(
    score: Decimal,
    maximum: Decimal,
) -> Decimal | None:
    if maximum <= 0:
        return None

    return _round_decimal(
        (
            score
            / maximum
        )
        * Decimal("100")
    )


def _unique_strings(
    values: Iterable[Any] | None,
) -> list[str]:
    result: list[str] = []

    for value in values or []:
        normalized = _text(
            value
        )

        if (
            normalized
            and normalized not in result
        ):
            result.append(
                normalized
            )

    return result


def _student_id(
    student: Mapping[str, Any],
) -> str:
    value = (
        student.get(
            "student_id"
        )
        or student.get(
            "_id"
        )
    )

    if value is None:
        raise ReportGenerationError(
            "student_id is required."
        )

    return str(value)


# =========================================================
# CURRICULUM HELPERS
# =========================================================

def _learning_area_id(
    learning_area: Mapping[str, Any],
) -> str:
    value = (
        learning_area.get(
            "learning_area_id"
        )
        or learning_area.get(
            "id"
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

    if value:
        return str(value)

    generated = (
        name.lower()
        .replace(
            " ",
            "_",
        )
    )

    if not generated:
        raise ReportGenerationError(
            "Learning area must have an ID or name."
        )

    return generated


def _learning_area_name(
    learning_area: Mapping[str, Any],
) -> str:
    return _text(
        learning_area.get(
            "name",
            learning_area.get(
                "subject"
            ),
        )
    )


def _normalize_curriculum(
    curriculum: Mapping[str, Any] | None,
) -> dict:
    if not isinstance(
        curriculum,
        Mapping,
    ):
        raise ReportGenerationError(
            "A valid school curriculum configuration is required."
        )

    raw_areas = curriculum.get(
        "learning_areas",
        [],
    )

    if not isinstance(
        raw_areas,
        list,
    ):
        raise ReportGenerationError(
            "Curriculum learning_areas must be an array."
        )

    areas = []

    seen: set[str] = set()

    for raw in raw_areas:
        if not isinstance(
            raw,
            Mapping,
        ):
            continue

        area = dict(raw)

        area_id = _learning_area_id(
            area
        )

        if area_id in seen:
            raise ReportGenerationError(
                f"Duplicate curriculum learning area: {area_id}"
            )

        name = _learning_area_name(
            area
        )

        if not name:
            raise ReportGenerationError(
                "Every curriculum learning area requires a name."
            )

        seen.add(
            area_id
        )

        area[
            "learning_area_id"
        ] = area_id

        area[
            "name"
        ] = name

        area[
            "include_in_report"
        ] = bool(
            area.get(
                "include_in_report",
                True,
            )
        )

        areas.append(
            area
        )

    areas.sort(
        key=lambda item: (
            item.get(
                "report_order",
                0,
            ),
            _lower(
                item.get(
                    "name"
                )
            ),
        )
    )

    return {
        **dict(curriculum),
        "learning_areas": areas,
    }


def _curriculum_area_map(
    curriculum: Mapping[str, Any],
) -> dict[str, dict]:
    result: dict[str, dict] = {}

    for area in curriculum.get(
        "learning_areas",
        [],
    ):
        if not isinstance(
            area,
            Mapping,
        ):
            continue

        normalized = dict(
            area
        )

        area_id = _learning_area_id(
            normalized
        )

        result[area_id] = normalized

        # Also permit matching by normalized name.
        name = _lower(
            _learning_area_name(
                normalized
            )
        )

        if name:
            result.setdefault(
                name,
                normalized,
            )

    return result


def _find_curriculum_area(
    assessment: Mapping[str, Any],
    area_map: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    explicit_id = _text(
        assessment.get(
            "learning_area_id"
        )
    )

    if explicit_id:
        found = area_map.get(
            explicit_id
        )

        if found:
            return found

    subject = _lower(
        assessment.get(
            "subject"
        )
    )

    if subject:
        return area_map.get(
            subject
        )

    learning_area = _lower(
        assessment.get(
            "learning_area"
        )
    )

    if learning_area:
        return area_map.get(
            learning_area
        )

    return None


# =========================================================
# PERFORMANCE SCALE
# =========================================================

DEFAULT_CBC_PERFORMANCE_SCALE = (
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


def _performance_scale(
    curriculum: Mapping[str, Any] | None,
    supplied_scale: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict]:
    values = supplied_scale

    if values is None and curriculum:
        values = curriculum.get(
            "performance_scale"
        )

    if values is None:
        values = DEFAULT_CBC_PERFORMANCE_SCALE

    result = []

    for raw in values:
        if not isinstance(
            raw,
            Mapping,
        ):
            continue

        code = _text(
            raw.get(
                "code"
            )
        ).upper()

        band = _text(
            raw.get(
                "band"
            )
        )

        if not code or not band:
            continue

        result.append(
            {
                "code": code,
                "band": band,
                "points": _safe_number(
                    raw.get(
                        "points"
                    )
                ),
                "description": _text(
                    raw.get(
                        "description"
                    )
                ),
            }
        )

    return result


def _performance_lookup(
    curriculum: Mapping[str, Any] | None,
    supplied_scale: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, dict]:
    return {
        item["code"]: item
        for item in _performance_scale(
            curriculum,
            supplied_scale,
        )
    }


# =========================================================
# GRADE SCALE
# =========================================================

def _grade_scale(
    curriculum: Mapping[str, Any] | None,
    supplied_scale: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict]:
    values = supplied_scale

    if values is None and curriculum:
        values = curriculum.get(
            "grading_scale"
        )

    result = []

    for raw in values or []:
        if not isinstance(
            raw,
            Mapping,
        ):
            continue

        minimum = _safe_decimal(
            raw.get(
                "min_percentage"
            ),
            Decimal("-1"),
        )

        if not (
            Decimal("0")
            <= minimum
            <= Decimal("100")
        ):
            continue

        grade = _text(
            raw.get(
                "grade"
            )
        )

        if not grade:
            continue

        result.append(
            {
                "min_percentage": minimum,
                "grade": grade,
                "points": _safe_number(
                    raw.get(
                        "points"
                    )
                ),
                "remark": (
                    _text(
                        raw.get(
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


def grade_for_percentage(
    percentage: Decimal | None,
    curriculum: Mapping[str, Any] | None = None,
    supplied_scale: Iterable[Mapping[str, Any]] | None = None,
) -> dict:
    """
    Resolve an optional traditional grade.

    CBC reports do not require letter grades. A grade is returned only
    when the school has configured a grading scale.
    """

    if percentage is None:
        return {
            "grade": None,
            "points": None,
            "remark": None,
        }

    for item in _grade_scale(
        curriculum,
        supplied_scale,
    ):
        if (
            percentage
            >= item[
                "min_percentage"
            ]
        ):
            return {
                "grade": item[
                    "grade"
                ],
                "points": item[
                    "points"
                ],
                "remark": item[
                    "remark"
                ],
            }

    return {
        "grade": None,
        "points": None,
        "remark": None,
    }


# =========================================================
# ASSESSMENT FILTERING
# =========================================================

def _filter_assessments(
    assessments: Iterable[Mapping[str, Any]],
    *,
    academic_year: str | None = None,
    term: str | None = None,
    assessment_name: str | None = None,
    assessment_type: str | None = None,
) -> list[dict]:
    result = []

    for raw in assessments:
        if not isinstance(
            raw,
            Mapping,
        ):
            continue

        assessment = dict(raw)

        if academic_year:
            if _text(
                assessment.get(
                    "academic_year"
                )
            ) != _text(
                academic_year
            ):
                continue

        if term:
            if _text(
                assessment.get(
                    "term"
                )
            ) != _text(
                term
            ):
                continue

        if assessment_name:
            actual = _lower(
                assessment.get(
                    "assessment_name"
                )
            )

            if actual != _lower(
                assessment_name
            ):
                continue

        if assessment_type:
            actual_type = (
                _lower(
                    assessment.get(
                        "assessment_type",
                        "assessment",
                    )
                )
                or "assessment"
            )

            if actual_type != _lower(
                assessment_type
            ):
                continue

        result.append(
            assessment
        )

    return result


def _assessment_sort_key(
    assessment: Mapping[str, Any],
) -> tuple:
    values = []

    for field in (
        "assessment_date",
        "updated_at",
        "created_at",
    ):
        value = assessment.get(
            field
        )

        if isinstance(
            value,
            datetime,
        ):
            values.append(
                value.isoformat()
            )
        else:
            values.append(
                _text(value)
            )

    return tuple(
        values
    )


# =========================================================
# ASSESSMENT EVIDENCE
# =========================================================

def _select_latest_subject_evidence(
    assessments: Iterable[Mapping[str, Any]],
) -> dict[str, dict]:
    """
    Select the most recent assessment evidence for each learning area.

    The report card itself remains curriculum-driven; this function
    simply resolves duplicate evidence records.
    """

    grouped: dict[str, list[dict]] = defaultdict(list)

    for raw in assessments:
        if not isinstance(
            raw,
            Mapping,
        ):
            continue

        subject = _lower(
            raw.get(
                "subject"
            )
        )

        learning_area = _lower(
            raw.get(
                "learning_area"
            )
        )

        key = (
            _text(
                raw.get(
                    "learning_area_id"
                )
            )
            or subject
            or learning_area
        )

        if not key:
            continue

        grouped[
            key
        ].append(
            dict(raw)
        )

    result = {}

    for key, rows in grouped.items():
        rows.sort(
            key=_assessment_sort_key,
            reverse=True,
        )

        result[
            key
        ] = rows[0]

    return result


# =========================================================
# STRANDS / COMPETENCIES
# =========================================================

def _extract_strand_evidence(
    assessment: Mapping[str, Any],
) -> list[dict]:
    """
    Support both compact and structured strand evidence stored by
    existing/new assessment writers.
    """

    output = []

    raw = assessment.get(
        "strands"
    )

    if isinstance(
        raw,
        list,
    ):
        for item in raw:
            if isinstance(
                item,
                Mapping,
            ):
                output.append(
                    {
                        "strand_id": _text(
                            item.get(
                                "strand_id",
                                item.get(
                                    "id"
                                ),
                            )
                        ) or None,
                        "strand": _text(
                            item.get(
                                "strand",
                                item.get(
                                    "name"
                                ),
                            )
                        ),
                        "sub_strand": _text(
                            item.get(
                                "sub_strand"
                            )
                        ) or None,
                        "performance_level": (
                            _text(
                                item.get(
                                    "performance_level"
                                )
                            ).upper()
                            or None
                        ),
                        "competency": _text(
                            item.get(
                                "competency"
                            )
                        ) or None,
                        "remarks": _text(
                            item.get(
                                "remarks"
                            )
                        ) or None,
                    }
                )

    raw_single = assessment.get(
        "strand"
    )

    if (
        isinstance(
            raw_single,
            str,
        )
        and raw_single.strip()
    ):
        output.append(
            {
                "strand_id": None,
                "strand": raw_single.strip(),
                "sub_strand": _text(
                    assessment.get(
                        "sub_strand"
                    )
                ) or None,
                "performance_level": (
                    _text(
                        assessment.get(
                            "performance_level"
                        )
                    ).upper()
                    or None
                ),
                "competency": _text(
                    assessment.get(
                        "competency"
                    )
                ) or None,
                "remarks": _text(
                    assessment.get(
                        "remarks"
                    )
                ) or None,
            }
        )

    return [
        item
        for item in output
        if item.get(
            "strand"
        )
    ]


def _extract_competencies(
    assessment: Mapping[str, Any],
) -> list[str]:
    values = []

    raw = assessment.get(
        "competencies"
    )

    if isinstance(
        raw,
        list,
    ):
        values.extend(
            raw
        )

    single = assessment.get(
        "competency"
    )

    if single:
        values.append(
            single
        )

    return _unique_strings(
        values
    )


# =========================================================
# PERFORMANCE LEVEL
# =========================================================

def _resolve_performance_level(
    assessment: Mapping[str, Any],
    curriculum: Mapping[str, Any] | None,
    performance_scale: Iterable[Mapping[str, Any]] | None = None,
) -> dict:
    stored_code = (
        _text(
            assessment.get(
                "performance_level"
            )
        ).upper()
        or _text(
            assessment.get(
                "competency_level"
            )
        ).upper()
    )

    lookup = _performance_lookup(
        curriculum,
        performance_scale,
    )

    if stored_code and stored_code in lookup:
        item = lookup[
            stored_code
        ]

        return {
            "code": item[
                "code"
            ],
            "band": item[
                "band"
            ],
            "points": item.get(
                "points"
            ),
            "description": item.get(
                "description"
            ),
            "source": "stored",
        }

    return {
        "code": None,
        "band": None,
        "points": None,
        "description": None,
        "source": None,
    }


# =========================================================
# SUBJECT / LEARNING AREA RESULT
# =========================================================

def generate_learning_area_result(
    learning_area: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    *,
    curriculum: Mapping[str, Any] | None = None,
    grading_scale: Iterable[Mapping[str, Any]] | None = None,
    performance_scale: Iterable[Mapping[str, Any]] | None = None,
) -> dict:
    """
    Build one CBC-aware learning-area row.

    The curriculum determines the presence and identity of the row.
    Assessment evidence determines its achievement data.
    """

    evidence = evidence or {}

    area_id = _learning_area_id(
        learning_area
    )

    area_name = _learning_area_name(
        learning_area
    )

    numeric_enabled = True

    if curriculum:
        settings = curriculum.get(
            "report_settings",
            {}
        ) or {}

        numeric_enabled = bool(
            settings.get(
                "allow_numeric_scores",
                True,
            )
        )

    score = None
    max_score = None
    percentage = None

    if numeric_enabled:
        raw_score = evidence.get(
            "score"
        )

        raw_max = evidence.get(
            "max_score"
        )

        if (
            raw_score is not None
            and raw_max is not None
        ):
            score_decimal = _safe_decimal(
                raw_score
            )

            max_decimal = _safe_decimal(
                raw_max
            )

            percentage_decimal = _percentage(
                score_decimal,
                max_decimal,
            )

            score = _json_number(
                score_decimal
            )

            max_score = _json_number(
                max_decimal
            )

            if percentage_decimal is not None:
                percentage = _json_number(
                    percentage_decimal
                )

    # Prefer stored percentage if available.
    if (
        numeric_enabled
        and evidence.get(
            "percentage"
        ) is not None
    ):
        percentage = _json_number(
            _safe_decimal(
                evidence.get(
                    "percentage"
                )
            )
        )

    grade_result = grade_for_percentage(
        (
            _safe_decimal(
                percentage
            )
            if percentage is not None
            else None
        ),
        curriculum,
        grading_scale,
    )

    performance = _resolve_performance_level(
        evidence,
        curriculum,
        performance_scale,
    )

    competencies = _extract_competencies(
        evidence
    )

    strands = _extract_strand_evidence(
        evidence
    )

    stored_grade = (
        _text(
            evidence.get(
                "grade"
            )
        )
        or None
    )

    remarks = (
        _text(
            evidence.get(
                "remarks"
            )
        )
        or grade_result.get(
            "remark"
        )
        or ""
    )

    competency_level = (
        _text(
            evidence.get(
                "competency_level"
            )
        )
        or None
    )

    return {
        # -------------------------------------------------
        # CURRICULUM IDENTITY
        # -------------------------------------------------

        "learning_area_id": area_id,

        "learning_area": area_name,

        "code": (
            _text(
                learning_area.get(
                    "code"
                )
            )
            or None
        ),

        "category": (
            _lower(
                learning_area.get(
                    "category",
                    "other",
                )
            )
            or "other"
        ),

        "pathway": (
            _lower(
                learning_area.get(
                    "pathway"
                )
            )
            or None
        ),

        "track": (
            _text(
                learning_area.get(
                    "track"
                )
            )
            or None
        ),

        # Backward compatibility.
        "subject": area_name,

        # -------------------------------------------------
        # NUMERIC EVIDENCE
        # -------------------------------------------------

        "score": score,

        "max_score": max_score,

        "percentage": percentage,

        # -------------------------------------------------
        # GRADING
        # -------------------------------------------------

        "grade": (
            stored_grade
            or grade_result.get(
                "grade"
            )
        ),

        "points": (
            grade_result.get(
                "points"
            )
        ),

        # -------------------------------------------------
        # CBC PERFORMANCE
        # -------------------------------------------------

        "performance_level": performance.get(
            "code"
        ),

        "performance_band": performance.get(
            "band"
        ),

        "performance_points": performance.get(
            "points"
        ),

        "competency_level": competency_level,

        "competencies": competencies,

        "strands": strands,

        "remarks": remarks,

        # -------------------------------------------------
        # EVIDENCE METADATA
        # -------------------------------------------------

        "assessment_name": _text(
            evidence.get(
                "assessment_name"
            )
        ) or None,

        "assessment_type": (
            _text(
                evidence.get(
                    "assessment_type",
                    "assessment",
                )
            ).lower()
            or "assessment"
        ),

        "assessment_date": (
            _text(
                evidence.get(
                    "assessment_date"
                )
            )
            or None
        ),

        "has_evidence": bool(
            evidence
        ),
    }


# =========================================================
# SUMMARY HELPERS
# =========================================================

def _numeric_summary(
    learning_areas: list[dict],
) -> dict:
    rows = [
        row
        for row in learning_areas
        if row.get(
            "percentage"
        ) is not None
    ]

    if not rows:
        return {
            "assessed_learning_areas": 0,
            "average_percentage": None,
            "total_score": None,
            "total_max_score": None,
        }

    percentages = [
        Decimal(
            str(
                row[
                    "percentage"
                ]
            )
        )
        for row in rows
    ]

    total_score = sum(
        (
            _safe_decimal(
                row.get(
                    "score"
                )
            )
            for row in rows
            if row.get(
                "score"
            ) is not None
        ),
        Decimal("0"),
    )

    total_max = sum(
        (
            _safe_decimal(
                row.get(
                    "max_score"
                )
            )
            for row in rows
            if row.get(
                "max_score"
            ) is not None
        ),
        Decimal("0"),
    )

    average = (
        sum(
            percentages,
            Decimal("0"),
        )
        / Decimal(
            str(
                len(
                    percentages
                )
            )
        )
    )

    return {
        "assessed_learning_areas": len(
            rows
        ),
        "average_percentage": _json_number(
            average
        ),
        "total_score": (
            _json_number(
                total_score
            )
            if total_max > 0
            else None
        ),
        "total_max_score": (
            _json_number(
                total_max
            )
            if total_max > 0
            else None
        ),
    }


def _competency_summary(
    learning_areas: list[dict],
) -> dict:
    level_counts = Counter()
    band_counts = Counter()
    competencies = Counter()

    for row in learning_areas:
        level = row.get(
            "performance_level"
        )

        band = row.get(
            "performance_band"
        )

        if level:
            level_counts[
                str(level)
            ] += 1

        if band:
            band_counts[
                str(band)
            ] += 1

        for competency in row.get(
            "competencies",
            [],
        ):
            competencies[
                str(competency)
            ] += 1

    dominant_level = (
        level_counts.most_common(1)[0][0]
        if level_counts
        else None
    )

    dominant_band = (
        band_counts.most_common(1)[0][0]
        if band_counts
        else None
    )

    return {
        "performance_level_counts": dict(
            level_counts
        ),

        "performance_band_counts": dict(
            band_counts
        ),

        "dominant_performance_level": dominant_level,

        "dominant_performance_band": dominant_band,

        "competencies": [
            {
                "name": name,
                "count": count,
            }
            for name, count in competencies.most_common()
        ],
    }


def _strand_summary(
    learning_areas: list[dict],
) -> list[dict]:
    grouped: dict[str, dict] = {}

    for row in learning_areas:
        for strand in row.get(
            "strands",
            [],
        ):
            name = _text(
                strand.get(
                    "strand"
                )
            )

            if not name:
                continue

            key = _lower(
                name
            )

            item = grouped.setdefault(
                key,
                {
                    "strand": name,
                    "learning_areas": [],
                    "performance_levels": [],
                    "competencies": [],
                    "remarks": [],
                },
            )

            if row.get(
                "learning_area"
            ):
                if row[
                    "learning_area"
                ] not in item[
                    "learning_areas"
                ]:
                    item[
                        "learning_areas"
                    ].append(
                        row[
                            "learning_area"
                        ]
                    )

            if strand.get(
                "performance_level"
            ):
                item[
                    "performance_levels"
                ].append(
                    strand[
                        "performance_level"
                    ]
                )

            competency = _text(
                strand.get(
                    "competency"
                )
            )

            if competency:
                if competency not in item[
                    "competencies"
                ]:
                    item[
                        "competencies"
                    ].append(
                        competency
                    )

            remark = _text(
                strand.get(
                    "remarks"
                )
            )

            if remark:
                item[
                    "remarks"
                ].append(
                    remark
                )

    return list(
        grouped.values()
    )


# =========================================================
# STUDENT EXAM REPORT
# =========================================================

def generate_student_exam_report(
    student: Mapping[str, Any],
    assessments: Iterable[Mapping[str, Any]],
    *,
    curriculum: Mapping[str, Any],
    academic_year: str | None = None,
    term: str | None = None,
    assessment_name: str | None = None,
    assessment_type: str | None = "exam",
    grading_scale: Iterable[Mapping[str, Any]] | None = None,
    performance_scale: Iterable[Mapping[str, Any]] | None = None,
    attendance: Mapping[str, Any] | None = None,
    teacher_remarks: str | None = None,
    principal_remarks: str | None = None,
    learner_remarks: str | None = None,
    class_position: int | None = None,
    class_size: int | None = None,
    ranking_enabled: bool = False,
    report_branding: Mapping[str, Any] | None = None,
    print_options: Mapping[str, Any] | None = None,
) -> dict:
    """
    Generate one CBC-aware learner report.

    The school's curriculum is mandatory and determines which
    learning areas are displayed.
    """

    if not isinstance(
        student,
        Mapping,
    ):
        raise ReportGenerationError(
            "student must be an object."
        )

    normalized_curriculum = _normalize_curriculum(
        curriculum
    )

    student_identifier = _student_id(
        student
    )

    settings = (
        normalized_curriculum.get(
            "report_settings",
            {}
        )
        or {}
    )

    include_empty = bool(
        settings.get(
            "include_empty_learning_areas",
            False,
        )
    )

    if not isinstance(
        assessments,
        Iterable,
    ):
        assessments = []

    filtered = _filter_assessments(
        assessments,
        academic_year=academic_year,
        term=term,
        assessment_name=assessment_name,
        assessment_type=assessment_type,
    )

    area_map = _curriculum_area_map(
        normalized_curriculum
    )

    # Assessment evidence indexed by learning area.
    evidence_by_area: dict[str, list[dict]] = defaultdict(list)

    for raw in filtered:
        if not isinstance(
            raw,
            Mapping,
        ):
            continue

        area = _find_curriculum_area(
            raw,
            area_map,
        )

        if area is None:
            # Ignore evidence for a subject/learning area that the
            # school has not configured for this curriculum.
            continue

        area_id = _learning_area_id(
            area
        )

        evidence_by_area[
            area_id
        ].append(
            dict(raw)
        )

    learning_area_rows: list[dict] = []

    for area in normalized_curriculum[
        "learning_areas"
    ]:
        if not area.get(
            "include_in_report",
            True,
        ):
            continue

        area_id = _learning_area_id(
            area
        )

        candidate_evidence = evidence_by_area.get(
            area_id,
            []
        )

        latest = None

        if candidate_evidence:
            candidate_evidence.sort(
                key=_assessment_sort_key,
                reverse=True,
            )

            latest = candidate_evidence[
                0
            ]

        if (
            latest is None
            and not include_empty
        ):
            # Do not put unassessed configured areas on the report
            # unless the school explicitly requested empty areas.
            continue

        row = generate_learning_area_result(
            area,
            latest,
            curriculum=normalized_curriculum,
            grading_scale=grading_scale,
            performance_scale=performance_scale,
        )

        learning_area_rows.append(
            row
        )

    # Keep the curriculum-defined order.
    learning_area_rows.sort(
        key=lambda row: (
            next(
                (
                    area.get(
                        "report_order",
                        0,
                    )
                    for area in normalized_curriculum[
                        "learning_areas"
                    ]
                    if _learning_area_id(
                        area
                    )
                    == row[
                        "learning_area_id"
                    ]
                ),
                0,
            ),
            _lower(
                row.get(
                    "learning_area"
                )
            ),
        )
    )

    numeric_summary = _numeric_summary(
        learning_area_rows
    )

    competency_summary = _competency_summary(
        learning_area_rows
    )

    strand_summary = _strand_summary(
        learning_area_rows
    )

    percentages = [
        Decimal(
            str(
                row[
                    "percentage"
                ]
            )
        )
        for row in learning_area_rows
        if row.get(
            "percentage"
        ) is not None
    ]

    overall_percentage = None

    if percentages:
        overall_percentage = _json_number(
            sum(
                percentages,
                Decimal("0"),
            )
            / Decimal(
                str(
                    len(
                        percentages
                    )
                )
            )
        )

    overall_grade = grade_for_percentage(
        (
            _safe_decimal(
                overall_percentage
            )
            if overall_percentage is not None
            else None
        ),
        normalized_curriculum,
        grading_scale,
    )

    dominant_performance_level = (
        competency_summary.get(
            "dominant_performance_level"
        )
    )

    dominant_performance_band = (
        competency_summary.get(
            "dominant_performance_band"
        )
    )

    resolved_academic_year = (
        _text(
            academic_year
        )
        or _text(
            normalized_curriculum.get(
                "academic_year"
            )
        )
        or (
            _text(
                filtered[0].get(
                    "academic_year"
                )
            )
            if filtered
            else ""
        )
    )

    resolved_term = (
        _text(
            term
        )
        or _text(
            normalized_curriculum.get(
                "term"
            )
        )
        or (
            _text(
                filtered[0].get(
                    "term"
                )
            )
            if filtered
            else ""
        )
    )

    resolved_assessment_name = (
        _text(
            assessment_name
        )
        or (
            _text(
                filtered[0].get(
                    "assessment_name"
                )
            )
            if filtered
            else ""
        )
    )

    resolved_assessment_type = (
        _lower(
            assessment_type
        )
        or "exam"
    )

    return {
        # -------------------------------------------------
        # LEARNER
        # -------------------------------------------------

        "student_id": student_identifier,

        "student_name": _text(
            student.get(
                "full_name",
                student.get(
                    "student_name"
                ),
            )
        ),

        "student_user_id": (
            _text(
                student.get(
                    "student_user_id"
                )
            )
            or None
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

        "class_id": (
            _text(
                student.get(
                    "class_id"
                )
            )
            or None
        ),

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

        # -------------------------------------------------
        # CURRICULUM
        # -------------------------------------------------

        "education_level": (
            _lower(
                normalized_curriculum.get(
                    "education_level"
                )
            )
            or None
        ),

        "grade": (
            _text(
                normalized_curriculum.get(
                    "grade"
                )
            )
            or None
        ),

        "pathway": (
            _lower(
                normalized_curriculum.get(
                    "pathway"
                )
            )
            or None
        ),

        "track": (
            _text(
                normalized_curriculum.get(
                    "track"
                )
            )
            or None
        ),

        "assessment_framework": (
            _lower(
                normalized_curriculum.get(
                    "assessment_framework",
                    "cbc",
                )
            )
            or "cbc"
        ),

        "report_type": (
            _lower(
                settings.get(
                    "report_type",
                    "individual_learner_report",
                )
            )
            or "individual_learner_report"
        ),

        # -------------------------------------------------
        # EXAM
        # -------------------------------------------------

        "academic_year": resolved_academic_year,

        "term": resolved_term,

        "assessment_name": resolved_assessment_name,

        "assessment_type": resolved_assessment_type,

        # -------------------------------------------------
        # LEARNING AREAS
        # -------------------------------------------------

        "learning_areas": learning_area_rows,

        # Compatibility alias.
        "subjects": learning_area_rows,

        "learning_area_count": len(
            learning_area_rows
        ),

        "subject_count": len(
            learning_area_rows
        ),

        # -------------------------------------------------
        # NUMERIC SUMMARY
        # -------------------------------------------------

        "numeric_summary": numeric_summary,

        "total_score": numeric_summary.get(
            "total_score"
        ),

        "total_max_score": numeric_summary.get(
            "total_max_score"
        ),

        "average_percentage": numeric_summary.get(
            "average_percentage"
        ),

        "overall_percentage": overall_percentage,

        # -------------------------------------------------
        # CBC SUMMARY
        # -------------------------------------------------

        "competency_summary": competency_summary,

        "strand_summary": strand_summary,

        "performance_levels": [
            {
                "learning_area": row[
                    "learning_area"
                ],
                "code": row.get(
                    "performance_level"
                ),
                "band": row.get(
                    "performance_band"
                ),
                "points": row.get(
                    "performance_points"
                ),
            }
            for row in learning_area_rows
            if row.get(
                "performance_level"
            )
        ],

        "competencies": _unique_strings(
            competency
            for row in learning_area_rows
            for competency in row.get(
                "competencies",
                [],
            )
        ),

        "overall_performance_level": (
            dominant_performance_level
        ),

        "overall_performance_band": (
            dominant_performance_band
        ),

        # -------------------------------------------------
        # OPTIONAL LETTER GRADE
        # -------------------------------------------------

        "overall_grade": (
            overall_grade.get(
                "grade"
            )
        ),

        "overall_points": (
            overall_grade.get(
                "points"
            )
        ),

        "overall_competency": (
            dominant_performance_band
        ),

        # -------------------------------------------------
        # RANKING
        # -------------------------------------------------

        "ranking_enabled": bool(
            ranking_enabled
        ),

        "class_position": (
            class_position
            if ranking_enabled
            else None
        ),

        "class_size": (
            class_size
            if ranking_enabled
            else None
        ),

        # -------------------------------------------------
        # ATTENDANCE
        # -------------------------------------------------

        "attendance": dict(
            attendance
            or {}
        ),

        # -------------------------------------------------
        # REMARKS
        # -------------------------------------------------

        "teacher_remarks": _text(
            teacher_remarks
        ),

        "principal_remarks": _text(
            principal_remarks
        ),

        "learner_remarks": _text(
            learner_remarks
        ),

        "strengths": _unique_strings(
            [
                *competency_summary.get(
                    "competencies",
                    []
                )
            ]
        ),

        "areas_for_improvement": [],

        "next_steps": [],

        # -------------------------------------------------
        # BRANDING / PRINT
        # -------------------------------------------------

        "report_branding": dict(
            report_branding
            or {}
        ),

        "print": dict(
            print_options
            or {}
        ),

        # -------------------------------------------------
        # GENERATION
        # -------------------------------------------------

        "generation_engine": "deterministic",

        "generation_version": GENERATOR_VERSION,
    }


# =========================================================
# CLASS REPORTS
# =========================================================

def assign_class_positions(
    reports: list[dict],
) -> list[dict]:
    """
    Competition ranking.

        95 -> 1
        90 -> 2
        90 -> 2
        80 -> 4

    Ranking is an optional school configuration.
    """

    ranked = [
        report
        for report in reports
        if report.get(
            "overall_percentage"
        ) is not None
    ]

    ranked.sort(
        key=lambda report: (
            -float(
                report[
                    "overall_percentage"
                ]
            ),
            _lower(
                report.get(
                    "student_name"
                )
            ),
        )
    )

    previous_percentage = None
    current_rank = 0

    for index, report in enumerate(
        ranked,
        start=1,
    ):
        percentage = float(
            report[
                "overall_percentage"
            ]
        )

        if (
            previous_percentage is None
            or percentage != previous_percentage
        ):
            current_rank = index

        report[
            "class_position"
        ] = current_rank

        previous_percentage = percentage

    class_size = len(
        ranked
    )

    for report in reports:
        if report in ranked:
            report[
                "class_size"
            ] = class_size
        else:
            report[
                "class_position"
            ] = None
            report[
                "class_size"
            ] = class_size

    return reports


def generate_class_exam_reports(
    students: Iterable[Mapping[str, Any]],
    assessments: Iterable[Mapping[str, Any]],
    *,
    curriculum: Mapping[str, Any],
    academic_year: str | None = None,
    term: str | None = None,
    assessment_name: str | None = None,
    assessment_type: str = "exam",
    grading_scale: Iterable[Mapping[str, Any]] | None = None,
    performance_scale: Iterable[Mapping[str, Any]] | None = None,
    attendance_by_student: Mapping[str, Mapping[str, Any]] | None = None,
    report_branding: Mapping[str, Any] | None = None,
    teacher_remarks: str | None = None,
    principal_remarks: str | None = None,
    ranking_enabled: bool = False,
) -> list[dict]:
    """
    Generate CBC-aware reports for a class.
    """

    assessment_list = [
        dict(item)
        for item in assessments
        if isinstance(
            item,
            Mapping,
        )
    ]

    attendance_map = (
        attendance_by_student
        or {}
    )

    reports = []

    for student in students:
        if not isinstance(
            student,
            Mapping,
        ):
            continue

        student_id = _student_id(
            student
        )

        student_assessments = [
            assessment
            for assessment in assessment_list
            if str(
                assessment.get(
                    "student_id"
                )
            )
            == student_id
        ]

        report = generate_student_exam_report(
            student,
            student_assessments,
            curriculum=curriculum,
            academic_year=academic_year,
            term=term,
            assessment_name=assessment_name,
            assessment_type=assessment_type,
            grading_scale=grading_scale,
            performance_scale=performance_scale,
            attendance=attendance_map.get(
                student_id,
                {},
            ),
            teacher_remarks=teacher_remarks,
            principal_remarks=principal_remarks,
            ranking_enabled=ranking_enabled,
            report_branding=report_branding,
        )

        reports.append(
            report
        )

    if ranking_enabled:
        reports = assign_class_positions(
            reports
        )

    return reports


# =========================================================
# POST-EXAM PROGRAMME HELPERS
# =========================================================

def _parse_date(
    value: str,
) -> date:
    try:
        return date.fromisoformat(
            value
        )
    except ValueError as exc:
        raise ReportGenerationError(
            f"Invalid date: {value}. Expected YYYY-MM-DD."
        ) from exc


def _time_to_minutes(
    value: str,
) -> int:
    value = _text(
        value
    )

    parts = value.split(":")

    if len(parts) != 2:
        raise ReportGenerationError(
            f"Invalid time: {value}. Expected HH:MM."
        )

    try:
        hours = int(
            parts[0]
        )
        minutes = int(
            parts[1]
        )
    except ValueError as exc:
        raise ReportGenerationError(
            f"Invalid time: {value}. Expected HH:MM."
        ) from exc

    if not (
        0 <= hours <= 23
        and 0 <= minutes <= 59
    ):
        raise ReportGenerationError(
            f"Invalid time: {value}."
        )

    return (
        hours * 60
        + minutes
    )


def _minutes_to_time(
    minutes: int,
) -> str:
    return (
        f"{minutes // 60:02d}:"
        f"{minutes % 60:02d}"
    )


def _school_days_between(
    start: date,
    end: date,
    avoid_weekends: bool,
) -> list[date]:
    if end < start:
        raise ReportGenerationError(
            "end_date cannot be before start_date."
        )

    days = []

    current = start

    while current <= end:
        if not (
            avoid_weekends
            and current.weekday() >= 5
        ):
            days.append(
                current
            )

        current += timedelta(
            days=1
        )

    return days


def _validate_activity(
    activity: Mapping[str, Any],
) -> dict:
    if not isinstance(
        activity,
        Mapping,
    ):
        raise ReportGenerationError(
            "Programme activity must be an object."
        )

    title = _text(
        activity.get(
            "title"
        )
    )

    if not title:
        raise ReportGenerationError(
            "Programme activity title is required."
        )

    start_time = (
        _text(
            activity.get(
                "start_time"
            )
        )
        or None
    )

    end_time = (
        _text(
            activity.get(
                "end_time"
            )
        )
        or None
    )

    if start_time and end_time:
        start = _time_to_minutes(
            start_time
        )

        end = _time_to_minutes(
            end_time
        )

        if end <= start:
            raise ReportGenerationError(
                f"Invalid time range for activity: {title}"
            )

    return {
        "activity_id": (
            _text(
                activity.get(
                    "activity_id"
                )
            )
            or None
        ),

        "title": title,

        "activity_type": (
            _lower(
                activity.get(
                    "activity_type",
                    "other",
                )
            )
            or "other"
        ),

        "description": _text(
            activity.get(
                "description"
            )
        ),

        "day": (
            _lower(
                activity.get(
                    "day"
                )
            )
            or None
        ),

        "start_time": start_time,

        "end_time": end_time,

        "audience": _unique_strings(
            activity.get(
                "audience"
            )
        ),

        "class_names": _unique_strings(
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
# POST-EXAM PROGRAMME GENERATOR
# =========================================================

def generate_post_exam_programme(
    *,
    start_date: str,
    end_date: str,
    activities: Iterable[Mapping[str, Any]],
    title: str = "Post-Examination School Programme",
    academic_year: str | None = None,
    term: str | None = None,
    daily_start_time: str = "08:00",
    daily_end_time: str = "16:00",
    avoid_weekends: bool = True,
    target_classes: Iterable[str] | None = None,
    target_students: Iterable[str] | None = None,
) -> dict:
    """
    Generate a deterministic post-examination school programme.

    Explicitly timed activities keep their times.
    Untimed activities are distributed across the daily window.
    """

    start = _parse_date(
        start_date
    )

    end = _parse_date(
        end_date
    )

    days = _school_days_between(
        start,
        end,
        avoid_weekends,
    )

    if not days:
        raise ReportGenerationError(
            "No school days exist in the selected date range."
        )

    normalized_activities = [
        _validate_activity(
            activity
        )
        for activity in activities
        if isinstance(
            activity,
            Mapping,
        )
    ]

    if not normalized_activities:
        raise ReportGenerationError(
            "At least one programme activity is required."
        )

    window_start = _time_to_minutes(
        daily_start_time
    )

    window_end = _time_to_minutes(
        daily_end_time
    )

    if window_end <= window_start:
        raise ReportGenerationError(
            "daily_end_time must be after daily_start_time."
        )

    generated = []

    # -----------------------------------------------------
    # Build a sensible cycle through the activities.
    # -----------------------------------------------------

    total_activities = len(
        normalized_activities
    )

    for day_index, current_day in enumerate(
        days
    ):
        # Rotate activities so a longer programme does not
        # put the exact same activity first every day.
        day_activities = []

        for offset in range(
            min(
                total_activities,
                6,
            )
        ):
            activity = normalized_activities[
                (
                    day_index
                    + offset
                )
                % total_activities
            ]

            day_activities.append(
                activity
            )

        explicit = []
        flexible = []

        for activity in day_activities:
            if (
                activity.get(
                    "start_time"
                )
                and activity.get(
                    "end_time"
                )
            ):
                explicit.append(
                    activity
                )
            else:
                flexible.append(
                    activity
                )

        # -------------------------------------------------
        # Reserve explicit activities.
        # -------------------------------------------------

        occupied = []

        for activity in explicit:
            start_minutes = _time_to_minutes(
                activity[
                    "start_time"
                ]
            )

            end_minutes = _time_to_minutes(
                activity[
                    "end_time"
                ]
            )

            if (
                start_minutes
                < window_start
                or end_minutes
                > window_end
            ):
                raise ReportGenerationError(
                    f"Activity '{activity['title']}' "
                    "falls outside the daily programme window."
                )

            occupied.append(
                (
                    start_minutes,
                    end_minutes,
                    activity,
                )
            )

        occupied.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        previous_end = None

        for start_minutes, end_minutes, activity in occupied:
            if (
                previous_end is not None
                and start_minutes
                < previous_end
            ):
                raise ReportGenerationError(
                    f"Overlapping programme activity: {activity['title']}"
                )

            previous_end = end_minutes

        # -------------------------------------------------
        # Find free windows.
        # -------------------------------------------------

        free_windows = []

        cursor = window_start

        for start_minutes, end_minutes, _ in occupied:
            if start_minutes > cursor:
                free_windows.append(
                    (
                        cursor,
                        start_minutes,
                    )
                )

            cursor = max(
                cursor,
                end_minutes,
            )

        if cursor < window_end:
            free_windows.append(
                (
                    cursor,
                    window_end,
                )
            )

        # -------------------------------------------------
        # Place flexible activities.
        # -------------------------------------------------

        flexible_index = 0

        for gap_start, gap_end in free_windows:
            while (
                flexible_index
                < len(flexible)
            ):
                remaining = (
                    len(
                        flexible
                    )
                    - flexible_index
                )

                available = (
                    gap_end
                    - gap_start
                )

                # Give each flexible activity at least 30 minutes.
                if available < 30:
                    break

                duration = max(
                    30,
                    available
                    // max(
                        1,
                        remaining,
                    ),
                )

                activity_end = min(
                    gap_end,
                    gap_start
                    + duration,
                )

                if (
                    activity_end
                    <= gap_start
                ):
                    break

                activity = flexible[
                    flexible_index
                ]

                occupied.append(
                    (
                        gap_start,
                        activity_end,
                        activity,
                    )
                )

                flexible_index += 1

                gap_start = activity_end

        # -------------------------------------------------
        # Generate day's final entries.
        # -------------------------------------------------

        occupied.sort(
            key=lambda item: (
                item[0],
                item[1],
                _lower(
                    item[2].get(
                        "title"
                    )
                ),
            )
        )

        for start_minutes, end_minutes, activity in occupied:
            generated.append(
                {
                    "activity_id": activity.get(
                        "activity_id"
                    ),

                    "title": activity[
                        "title"
                    ],

                    "activity_type": activity.get(
                        "activity_type",
                        "other",
                    ),

                    "description": activity.get(
                        "description",
                        "",
                    ),

                    "date": current_day.isoformat(),

                    "day": current_day.strftime(
                        "%A"
                    ).lower(),

                    "start_time": _minutes_to_time(
                        start_minutes
                    ),

                    "end_time": _minutes_to_time(
                        end_minutes
                    ),

                    "audience": list(
                        activity.get(
                            "audience",
                            [],
                        )
                    ),

                    "class_names": list(
                        activity.get(
                            "class_names",
                            [],
                        )
                    ),

                    "facilitator": activity.get(
                        "facilitator"
                    ),

                    "venue": activity.get(
                        "venue"
                    ),

                    "notes": activity.get(
                        "notes",
                        "",
                    ),
                }
            )

    return {
        "title": (
            _text(
                title
            )
            or "Post-Examination School Programme"
        ),

        "description": (
            "Deterministically generated "
            "post-examination school programme."
        ),

        "academic_year": (
            _text(
                academic_year
            )
        ),

        "term": (
            _text(
                term
            )
        ),

        "programme_type": "post_exam",

        "start_date": days[0].isoformat(),

        "end_date": days[-1].isoformat(),

        "activities": generated,

        "activity_count": len(
            generated
        ),

        "target_classes": _unique_strings(
            target_classes
        ),

        "target_students": _unique_strings(
            target_students
        ),

        "generation_engine": "deterministic",

        "generation_version": GENERATOR_VERSION,
    }


# =========================================================
# REPORT QUALITY CHECK
# =========================================================

def validate_generated_report(
    report: Mapping[str, Any],
    curriculum: Mapping[str, Any],
) -> dict:
    """
    Lightweight structural safety check before the service persists
    the generated report.
    """

    errors = []

    if not isinstance(
        report,
        Mapping,
    ):
        return {
            "valid": False,
            "errors": [
                "Generated report must be an object."
            ],
        }

    normalized_curriculum = _normalize_curriculum(
        curriculum
    )

    allowed_ids = {
        _learning_area_id(
            area
        )
        for area in normalized_curriculum[
            "learning_areas"
        ]
        if area.get(
            "include_in_report",
            True,
        )
    }

    for row in report.get(
        "learning_areas",
        [],
    ):
        if not isinstance(
            row,
            Mapping,
        ):
            errors.append(
                "Learning-area report row must be an object."
            )
            continue

        area_id = _text(
            row.get(
                "learning_area_id"
            )
        )

        if (
            area_id
            and area_id not in allowed_ids
        ):
            errors.append(
                f"Report contains unconfigured learning area: {area_id}"
            )

    overall_percentage = report.get(
        "overall_percentage"
    )

    if overall_percentage is not None:
        try:
            percentage = float(
                overall_percentage
            )

            if not (
                0
                <= percentage
                <= 100
            ):
                errors.append(
                    "overall_percentage must be between 0 and 100."
                )
        except (
            TypeError,
            ValueError,
        ):
            errors.append(
                "overall_percentage must be numeric."
            )

    return {
        "valid": not errors,
        "errors": errors,
    }