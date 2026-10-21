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

    if (value is None or value == "") and not required:
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


def _items(data, key, maximum=20, item_max=80):
    value = data.get(key, [])

    if value is None or value == "":
        return []

    if isinstance(value, str):
        value = [part.strip() for part in value.replace(";", ",").split(",")]

    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{key} must be a list or comma-separated text.")

    result = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"Each {key} item must be text.")
        item = item.strip()
        if not item:
            continue
        if len(item) > item_max:
            raise ValueError(f"An item in {key} is too long.")
        if item.casefold() not in {entry.casefold() for entry in result}:
            result.append(item)
        if len(result) > maximum:
            raise ValueError(f"{key} may contain at most {maximum} items.")

    return result


def _boolean(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    raise ValueError("Boolean values must be true or false.")


def farmer_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    experience = _number(data, "experience_years", False)
    if experience > 80 or int(experience) != experience:
        raise ValueError("experience_years must be a whole number from 0 to 80.")

    return {
        "farmer_name": _text(data, "farmer_name", True, 160),
        "phone": _text(data, "phone", True, 30),
        "county": _text(data, "county", True, 100),
        "town": _text(data, "town", True, 100),
        "location": _text(data, "location", False, 200),
        "farm_name": _text(data, "farm_name", False, 160),
        "farm_count": 1,
        "farm_size": _number(data, "farm_size", False),
        "farm_size_unit": _text(data, "farm_size_unit", False, 30) or "acres",
        "farming_type": _text(data, "farming_type", True, 60),
        "experience_years": int(experience),
        "primary_crops": _items(data, "primary_crops"),
        "livestock": _items(data, "livestock"),
        "soil_type": _text(data, "soil_type", False, 100),
        "water_source": _text(data, "water_source", False, 100),
        "irrigation_available": _boolean(data.get("irrigation_available"), False),
        "primary_goal": _text(data, "primary_goal", False, 60) or "food_and_income",
        "target_market": _text(data, "target_market", False, 160),
        "description": _text(data, "description", False, 1000),
    }


def farmer_review_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    decision = _text(data, "decision", True, 30).lower()
    if decision not in {"approved", "rejected", "more_info"}:
        raise ValueError("Decision must be approved, rejected or more_info.")

    notes = _text(data, "review_notes", False, 800)
    if decision in {"rejected", "more_info"} and not notes:
        raise ValueError("Review notes are required when rejecting or requesting more information.")

    return {"decision": decision, "review_notes": notes}


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
        "irrigation": _boolean(data.get("irrigation"), False),
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