from __future__ import annotations


def _text(data, key, required=False, max_len=300):
    value = data.get(key, "")

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")

    value = value.strip()

    if required and not value:
        raise ValueError(f"{key} is required.")

    if len(value) > max_len:
        raise ValueError(f"{key} is too long.")

    return value


def _number(data, key, required=False, minimum=0):
    value = data.get(key)

    if value is None and not required:
        return 0.0

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number.")

    if value < minimum:
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    return value


def farmer_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "farm_name": _text(
            data, "farm_name", False, 160
        ),
        "farmer_name": _text(
            data, "farmer_name", True, 160
        ),
        "phone": _text(
            data, "phone", False, 30
        ),
        "county": _text(
            data, "county", False, 100
        ),
        "town": _text(
            data, "town", False, 100
        ),
        "location": _text(
            data, "location", False, 200
        ),
        "farm_size": _number(
            data, "farm_size", False
        ),
        "farm_size_unit": _text(
            data, "farm_size_unit", False, 30
        ) or "acres",
        "farming_type": _text(
            data, "farming_type", False, 60
        ) or "mixed",
        "description": _text(
            data, "description", False, 1000
        ),
    }


def farm_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "name": _text(data, "name", True, 160),
        "county": _text(data, "county", False, 100),
        "town": _text(data, "town", False, 100),
        "location": _text(data, "location", False, 200),
        "size": _number(data, "size", False),
        "size_unit": _text(
            data, "size_unit", False, 30
        ) or "acres",
        "soil_type": _text(
            data, "soil_type", False, 100
        ),
        "irrigation": bool(
            data.get("irrigation", False)
        ),
        "description": _text(
            data, "description", False, 1000
        ),
    }


def crop_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "name": _text(data, "name", True, 120),
        "variety": _text(
            data, "variety", False, 120
        ),
        "season": _text(
            data, "season", False, 80
        ),
        "area": _number(data, "area", False),
        "area_unit": _text(
            data, "area_unit", False, 30
        ) or "acres",
        "planting_date": _text(
            data, "planting_date", False, 40
        ),
        "expected_harvest_date": _text(
            data,
            "expected_harvest_date",
            False,
            40,
        ),
        "status": _text(
            data, "status", False, 40
        ) or "growing",
        "notes": _text(
            data, "notes", False, 1000
        ),
    }


def activity_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "type": _text(
            data, "type", True, 100
        ),
        "description": _text(
            data, "description", False, 1000
        ),
        "cost": _number(
            data, "cost", False
        ),
        "currency": _text(
            data, "currency", False, 8
        ) or "KES",
        "activity_date": _text(
            data, "activity_date", False, 40
        ),
    }


def harvest_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "crop_id": (
            str(data["crop_id"])
            if data.get("crop_id")
            else None
        ),
        "crop_name": _text(
            data, "crop_name", True, 120
        ),
        "quantity": _number(
            data, "quantity", True
        ),
        "unit": _text(
            data, "unit", False, 30
        ) or "kg",
        "quality": _text(
            data, "quality", False, 80
        ),
        "harvest_date": _text(
            data, "harvest_date", False, 40
        ),
        "notes": _text(
            data, "notes", False, 1000
        ),
    }