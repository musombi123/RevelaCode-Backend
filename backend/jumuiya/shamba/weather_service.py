"""Live weather integration for Shamba, backed by Open-Meteo (no API key required)."""
from __future__ import annotations

import threading
import time
from typing import Any

import requests

from backend.jumuiya.core.errors import APIError

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 600
_REQUEST_TIMEOUT_SECONDS = 8

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _location_label(farm: dict[str, Any]) -> str:
    parts = [
        str(farm.get("town") or "").strip(),
        str(farm.get("county") or "").strip(),
        str(farm.get("location") or "").strip(),
    ]
    unique = []
    for part in parts:
        if part and part.lower() not in {item.lower() for item in unique}:
            unique.append(part)
    if unique and "kenya" not in {item.lower() for item in unique}:
        unique.append("Kenya")
    return ", ".join(unique)


def _resolve_coordinates(farm: dict[str, Any]) -> tuple[float, float, str]:
    lat = _number(farm.get("latitude"))
    lon = _number(farm.get("longitude"))
    label = _location_label(farm)

    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon, label or "Farm GPS location"

    if not label or label == "Kenya":
        raise APIError(
            "Add a town or county to this farm, or share its device location, to get local weather.",
            422,
            "farm_location_required",
        )

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": label, "count": 5, "language": "en", "format": "json"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "RevelaCode-Shamba/1.0"},
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except (requests.RequestException, ValueError) as exc:
        raise APIError(
            "The weather location service is temporarily unavailable. Try again shortly.",
            502,
            "weather_geocoding_unavailable",
        ) from exc

    # Prefer a Kenyan match when the provider returns country metadata.
    match = next(
        (item for item in results if str(item.get("country_code") or "").upper() == "KE"),
        results[0] if results else None,
    )
    if not match:
        raise APIError(
            "We could not locate this farm from its saved town/county. Add GPS coordinates or update the farm location.",
            422,
            "weather_location_not_found",
        )

    return float(match["latitude"]), float(match["longitude"]), (
        match.get("name") or label
    )


def _weather_code_label(code: Any) -> str:
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "Conditions unavailable"

    if code == 0:
        return "Clear sky"
    if code in (1, 2):
        return "Mainly clear"
    if code == 3:
        return "Overcast"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67):
        return "Rain"
    if code in (71, 73, 75, 77):
        return "Snow or ice"
    if code in (80, 81, 82):
        return "Rain showers"
    if code in (85, 86):
        return "Snow showers"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Conditions unavailable"


def get_farm_weather(farm: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    """Return current conditions and a seven-day forecast for one farm."""
    lat, lon, label = _resolve_coordinates(farm)
    cache_key = f"{lat:.4f},{lon:.4f}"

    with _cache_lock:
        cached = _cache.get(cache_key)
        if not force_refresh and cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return {**cached[1], "cached": True}

    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
        "forecast_days": 7,
        "current": ",".join([
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "is_day", "precipitation", "rain", "showers", "weather_code",
            "wind_speed_10m", "wind_direction_10m",
        ]),
        "hourly": ",".join([
            "temperature_2m", "precipitation_probability", "precipitation",
            "weather_code",
        ]),
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_sum", "precipitation_probability_max",
            "wind_speed_10m_max", "sunrise", "sunset",
        ]),
    }

    try:
        response = requests.get(
            FORECAST_URL,
            params=params,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "RevelaCode-Shamba/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise APIError(
            "Live weather could not be reached right now. Check your connection and retry.",
            502,
            "weather_provider_unavailable",
        ) from exc

    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    hourly = payload.get("hourly") or {}

    daily_forecast = []
    days = daily.get("time") or []
    for index, day in enumerate(days):
        def at(key: str):
            values = daily.get(key) or []
            return values[index] if index < len(values) else None

        code = at("weather_code")
        daily_forecast.append({
            "date": day,
            "condition_code": code,
            "condition": _weather_code_label(code),
            "temperature_max_c": at("temperature_2m_max"),
            "temperature_min_c": at("temperature_2m_min"),
            "rainfall_mm": at("precipitation_sum"),
            "rain_probability_percent": at("precipitation_probability_max"),
            "wind_speed_max_kmh": at("wind_speed_10m_max"),
            "sunrise": at("sunrise"),
            "sunset": at("sunset"),
        })

    hourly_forecast = []
    hours = hourly.get("time") or []
    for index, hour in enumerate(hours[:24]):
        def at_hour(key: str):
            values = hourly.get(key) or []
            return values[index] if index < len(values) else None

        hourly_forecast.append({
            "time": hour,
            "temperature_c": at_hour("temperature_2m"),
            "rain_probability_percent": at_hour("precipitation_probability"),
            "rainfall_mm": at_hour("precipitation"),
            "condition_code": at_hour("weather_code"),
            "condition": _weather_code_label(at_hour("weather_code")),
        })

    result = {
        "provider": "Open-Meteo",
        "provider_url": "https://open-meteo.com/",
        "location": {
            "label": label,
            "latitude": lat,
            "longitude": lon,
            "timezone": payload.get("timezone"),
            "timezone_abbreviation": payload.get("timezone_abbreviation"),
        },
        "current": {
            "time": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "feels_like_c": current.get("apparent_temperature"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"),
            "rain_mm": current.get("rain"),
            "showers_mm": current.get("showers"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "wind_direction_degrees": current.get("wind_direction_10m"),
            "is_day": current.get("is_day"),
            "condition_code": current.get("weather_code"),
            "condition": _weather_code_label(current.get("weather_code")),
        },
        "hourly": hourly_forecast,
        "daily": daily_forecast,
        "units": payload.get("current_units") or {},
        "updated_at_epoch": int(time.time()),
        "cached": False,
        "attribution": "Weather data by Open-Meteo",
    }

    with _cache_lock:
        _cache[cache_key] = (time.time(), result)
    return result
