# backend/jumuiya/biashara/intelligence/geography.py

from __future__ import annotations

import math
import re
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================

EARTH_RADIUS_KM = 6371.0088

MAX_LATITUDE = 90.0
MIN_LATITUDE = -90.0

MAX_LONGITUDE = 180.0
MIN_LONGITUDE = -180.0


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_name(
    value: Any,
) -> str:
    """
    Normalize an area/business location name for comparison.
    """

    if value is None:
        return ""

    value = str(value).strip().lower()

    value = re.sub(
        r"[\s_-]+",
        " ",
        value,
    )

    return value.strip()


def slugify_area(
    value: Any,
) -> str:
    """
    Convert an area name into a stable identifier.
    """

    value = normalize_name(
        value
    )

    value = re.sub(
        r"[^a-z0-9\s-]",
        "",
        value,
    )

    value = re.sub(
        r"[\s_-]+",
        "-",
        value,
    )

    return (
        value.strip("-")
        or "area"
    )


# =========================================================
# COORDINATE VALIDATION
# =========================================================

def is_valid_latitude(
    latitude: Any,
) -> bool:
    try:
        value = float(
            latitude
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    return (
        MIN_LATITUDE
        <= value
        <= MAX_LATITUDE
    )


def is_valid_longitude(
    longitude: Any,
) -> bool:
    try:
        value = float(
            longitude
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    return (
        MIN_LONGITUDE
        <= value
        <= MAX_LONGITUDE
    )


def validate_coordinates(
    latitude: Any,
    longitude: Any,
) -> tuple[float, float]:
    """
    Validate and return normalized latitude/longitude.
    """

    try:
        latitude = float(
            latitude
        )
        longitude = float(
            longitude
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Valid latitude and longitude are required."
        )

    if not is_valid_latitude(
        latitude
    ):
        raise ValueError(
            "Latitude must be between -90 and 90."
        )

    if not is_valid_longitude(
        longitude
    ):
        raise ValueError(
            "Longitude must be between -180 and 180."
        )

    return (
        latitude,
        longitude,
    )


# =========================================================
# POINT
# =========================================================

def point(
    latitude: Any,
    longitude: Any,
) -> dict[str, float]:
    """
    Create a normalized geographic point.
    """

    latitude, longitude = (
        validate_coordinates(
            latitude,
            longitude,
        )
    )

    return {
        "latitude": latitude,
        "longitude": longitude,
    }


# =========================================================
# HAVERSINE DISTANCE
# =========================================================

def distance_km(
    latitude_a: Any,
    longitude_a: Any,
    latitude_b: Any,
    longitude_b: Any,
) -> float:
    """
    Calculate great-circle distance between two
    geographic points using the Haversine formula.
    """

    latitude_a, longitude_a = (
        validate_coordinates(
            latitude_a,
            longitude_a,
        )
    )

    latitude_b, longitude_b = (
        validate_coordinates(
            latitude_b,
            longitude_b,
        )
    )

    lat1 = math.radians(
        latitude_a
    )

    lat2 = math.radians(
        latitude_b
    )

    delta_lat = math.radians(
        latitude_b - latitude_a
    )

    delta_lon = math.radians(
        longitude_b - longitude_a
    )

    a = (
        math.sin(
            delta_lat / 2
        ) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(
            delta_lon / 2
        ) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(
            1 - a
        ),
    )

    return round(
        EARTH_RADIUS_KM * c,
        3,
    )


# =========================================================
# BOUNDING BOX
# =========================================================

def bounding_box(
    latitude: Any,
    longitude: Any,
    radius_km: Any,
) -> dict[str, float]:
    """
    Create an approximate geographic bounding box
    around a point.

    Useful when finding nearby market areas.
    """

    latitude, longitude = (
        validate_coordinates(
            latitude,
            longitude,
        )
    )

    try:
        radius_km = float(
            radius_km
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "radius_km must be a number."
        )

    if radius_km < 0:
        raise ValueError(
            "radius_km cannot be negative."
        )

    lat_delta = (
        radius_km
        / 111.32
    )

    cos_latitude = max(
        math.cos(
            math.radians(
                latitude
            )
        ),
        0.01,
    )

    lon_delta = (
        radius_km
        / (
            111.32
            * cos_latitude
        )
    )

    return {
        "min_latitude": max(
            MIN_LATITUDE,
            latitude - lat_delta,
        ),
        "max_latitude": min(
            MAX_LATITUDE,
            latitude + lat_delta,
        ),
        "min_longitude": max(
            MIN_LONGITUDE,
            longitude - lon_delta,
        ),
        "max_longitude": min(
            MAX_LONGITUDE,
            longitude + lon_delta,
        ),
    }


# =========================================================
# CENTER OF POINTS
# =========================================================

def centroid(
    coordinates: list,
) -> dict[str, float]:
    """
    Calculate the average center of a collection
    of latitude/longitude points.

    This is intended for small local areas rather
    than global geographic datasets.
    """

    if not isinstance(
        coordinates,
        list,
    ):
        raise ValueError(
            "coordinates must be a list."
        )

    if not coordinates:
        raise ValueError(
            "At least one coordinate is required."
        )

    latitude_total = 0.0
    longitude_total = 0.0

    valid_count = 0

    for coordinate in coordinates:

        if isinstance(
            coordinate,
            dict,
        ):

            latitude = coordinate.get(
                "latitude"
            )

            longitude = coordinate.get(
                "longitude"
            )

        elif (
            isinstance(
                coordinate,
                (list, tuple),
            )
            and len(coordinate) >= 2
        ):

            latitude = coordinate[0]
            longitude = coordinate[1]

        else:

            raise ValueError(
                "Each coordinate must be an object or [latitude, longitude]."
            )

        latitude, longitude = (
            validate_coordinates(
                latitude,
                longitude,
            )
        )

        latitude_total += latitude
        longitude_total += longitude

        valid_count += 1

    return {
        "latitude": round(
            latitude_total
            / valid_count,
            8,
        ),
        "longitude": round(
            longitude_total
            / valid_count,
            8,
        ),
    }


# =========================================================
# AREA NORMALIZATION
# =========================================================

def normalize_area(
    area: dict,
) -> dict:
    """
    Normalize a configured market area.

    Expected minimum structure:

        {
            "id": "nyali",
            "name": "Nyali",
            "sub_county": "Nyali",
            "county": "Mombasa",
            "center": {
                "latitude": ...,
                "longitude": ...
            }
        }
    """

    if not isinstance(
        area,
        dict,
    ):
        raise ValueError(
            "Area must be an object."
        )

    name = str(
        area.get(
            "name",
            ""
        )
    ).strip()

    if not name:
        raise ValueError(
            "Area name is required."
        )

    center = area.get(
        "center"
    )

    if not isinstance(
        center,
        dict,
    ):
        raise ValueError(
            f"Area '{name}' requires a center object."
        )

    latitude, longitude = (
        validate_coordinates(
            center.get(
                "latitude"
            ),
            center.get(
                "longitude"
            ),
        )
    )

    area_id = (
        str(
            area.get(
                "id",
                ""
            )
        ).strip()
        or slugify_area(
            name
        )
    )

    normalized = dict(
        area
    )

    normalized[
        "id"
    ] = area_id

    normalized[
        "name"
    ] = name

    normalized[
        "normalized_name"
    ] = normalize_name(
        name
    )

    normalized[
        "center"
    ] = {
        "latitude": latitude,
        "longitude": longitude,
    }

    if "sub_county" in normalized:
        normalized[
            "sub_county"
        ] = str(
            normalized[
                "sub_county"
            ]
        ).strip()

    if "county" in normalized:
        normalized[
            "county"
        ] = str(
            normalized[
                "county"
            ]
        ).strip()

    return normalized


# =========================================================
# AREA LOOKUP
# =========================================================

def find_area(
    areas: list[dict],
    identifier: Any,
):
    """
    Find an area by ID, name, or normalized name.
    """

    if not isinstance(
        areas,
        list,
    ):
        raise ValueError(
            "areas must be a list."
        )

    target = normalize_name(
        identifier
    )

    if not target:
        return None

    for raw_area in areas:

        if not isinstance(
            raw_area,
            dict,
        ):
            continue

        area = normalize_area(
            raw_area
        )

        candidates = {
            normalize_name(
                area.get(
                    "id"
                )
            ),
            normalize_name(
                area.get(
                    "name"
                )
            ),
            normalize_name(
                area.get(
                    "sub_county"
                )
            ),
        }

        if target in candidates:
            return area

    return None


# =========================================================
# NEAREST AREA
# =========================================================

def nearest_area(
    areas: list[dict],
    latitude: Any,
    longitude: Any,
):
    """
    Find the configured area closest to a geographic point.

    Returns the normalized area plus distance_km.
    """

    latitude, longitude = (
        validate_coordinates(
            latitude,
            longitude,
        )
    )

    if not areas:
        return None

    closest = None
    closest_distance = None

    for raw_area in areas:

        area = normalize_area(
            raw_area
        )

        center = area[
            "center"
        ]

        distance = distance_km(
            latitude,
            longitude,
            center[
                "latitude"
            ],
            center[
                "longitude"
            ],
        )

        if (
            closest_distance is None
            or distance < closest_distance
        ):

            closest = area
            closest_distance = distance

    if closest is None:
        return None

    return {
        "area": closest,
        "distance_km": closest_distance,
    }


# =========================================================
# POINT-IN-BOX
# =========================================================

def point_in_bounding_box(
    latitude: Any,
    longitude: Any,
    box: dict,
) -> bool:
    """
    Determine whether a point falls inside a bounding box.
    """

    latitude, longitude = (
        validate_coordinates(
            latitude,
            longitude,
        )
    )

    if not isinstance(
        box,
        dict,
    ):
        return False

    try:

        return (
            float(
                box["min_latitude"]
            )
            <= latitude
            <= float(
                box["max_latitude"]
            )
            and
            float(
                box["min_longitude"]
            )
            <= longitude
            <= float(
                box["max_longitude"]
            )
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return False


# =========================================================
# MAP SELECTION NORMALIZATION
# =========================================================

def normalize_map_selection(
    selection: dict,
) -> dict:
    """
    Normalize frontend map selection into a consistent
    structure understood by the intelligence engine.

    Supported selection styles:

        {
            "area_id": "nyali"
        }

    or:

        {
            "area_id": "nyali",
            "center": {
                "latitude": ...,
                "longitude": ...
            }
        }

    or a drawn geographic box:

        {
            "bounds": {
                "min_latitude": ...,
                "max_latitude": ...,
                "min_longitude": ...,
                "max_longitude": ...
            }
        }
    """

    if not isinstance(
        selection,
        dict,
    ):
        raise ValueError(
            "Map selection must be an object."
        )

    result = {}

    area_id = selection.get(
        "area_id"
    )

    if area_id:
        result[
            "area_id"
        ] = str(
            area_id
        ).strip()

    center = selection.get(
        "center"
    )

    if center:

        if not isinstance(
            center,
            dict,
        ):
            raise ValueError(
                "center must be an object."
            )

        result[
            "center"
        ] = point(
            center.get(
                "latitude"
            ),
            center.get(
                "longitude"
            ),
        )

    bounds = selection.get(
        "bounds"
    )

    if bounds:

        if not isinstance(
            bounds,
            dict,
        ):
            raise ValueError(
                "bounds must be an object."
            )

        required = [
            "min_latitude",
            "max_latitude",
            "min_longitude",
            "max_longitude",
        ]

        for key in required:

            if key not in bounds:
                raise ValueError(
                    f"bounds.{key} is required."
                )

        normalized_bounds = {
            key: float(
                bounds[key]
            )
            for key in required
        }

        if (
            not is_valid_latitude(
                normalized_bounds[
                    "min_latitude"
                ]
            )
            or
            not is_valid_latitude(
                normalized_bounds[
                    "max_latitude"
                ]
            )
        ):
            raise ValueError(
                "Invalid latitude bounds."
            )

        if (
            not is_valid_longitude(
                normalized_bounds[
                    "min_longitude"
                ]
            )
            or
            not is_valid_longitude(
                normalized_bounds[
                    "max_longitude"
                ]
            )
        ):
            raise ValueError(
                "Invalid longitude bounds."
            )

        if (
            normalized_bounds[
                "min_latitude"
            ]
            >
            normalized_bounds[
                "max_latitude"
            ]
        ):
            raise ValueError(
                "min_latitude cannot exceed max_latitude."
            )

        if (
            normalized_bounds[
                "min_longitude"
            ]
            >
            normalized_bounds[
                "max_longitude"
            ]
        ):
            raise ValueError(
                "min_longitude cannot exceed max_longitude."
            )

        result[
            "bounds"
        ] = normalized_bounds

    if not result:
        raise ValueError(
            "A map selection requires an area_id, center, or bounds."
        )

    return result


# =========================================================
# AREA DISTANCE
# =========================================================

def area_distance(
    area: dict,
    latitude: Any,
    longitude: Any,
) -> float:
    """
    Calculate distance from an area center to a point.
    """

    area = normalize_area(
        area
    )

    latitude, longitude = (
        validate_coordinates(
            latitude,
            longitude,
        )
    )

    return distance_km(
        area["center"]["latitude"],
        area["center"]["longitude"],
        latitude,
        longitude,
    )


# =========================================================
# EXPORT HELPERS
# =========================================================

__all__ = [
    "normalize_name",
    "slugify_area",
    "is_valid_latitude",
    "is_valid_longitude",
    "validate_coordinates",
    "point",
    "distance_km",
    "bounding_box",
    "centroid",
    "normalize_area",
    "find_area",
    "nearest_area",
    "point_in_bounding_box",
    "normalize_map_selection",
    "area_distance",
]
