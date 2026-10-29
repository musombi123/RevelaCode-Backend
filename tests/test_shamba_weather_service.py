from __future__ import annotations

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.shamba import weather_service


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def forecast_payload():
    return {
        "timezone": "Africa/Nairobi",
        "timezone_abbreviation": "EAT",
        "current_units": {"temperature_2m": "°C"},
        "current": {
            "time": "2026-10-29T19:00",
            "temperature_2m": 24.2,
            "relative_humidity_2m": 68,
            "apparent_temperature": 25.1,
            "precipitation": 0.2,
            "rain": 0.2,
            "showers": 0,
            "wind_speed_10m": 11.4,
            "wind_direction_10m": 120,
            "is_day": 0,
            "weather_code": 61,
        },
        "hourly": {
            "time": ["2026-10-29T19:00", "2026-10-29T20:00"],
            "temperature_2m": [24.2, 23.7],
            "precipitation_probability": [55, 60],
            "precipitation": [0.2, 0.5],
            "weather_code": [61, 63],
        },
        "daily": {
            "time": ["2026-10-29", "2026-10-30"],
            "weather_code": [61, 3],
            "temperature_2m_max": [28.0, 29.0],
            "temperature_2m_min": [19.0, 20.0],
            "precipitation_sum": [8.2, 0.0],
            "precipitation_probability_max": [80, 10],
            "wind_speed_10m_max": [18.0, 12.0],
            "sunrise": ["2026-10-29T06:10", "2026-10-30T06:10"],
            "sunset": ["2026-10-29T18:20", "2026-10-30T18:20"],
        },
    }


def test_weather_code_is_mapped_to_readable_condition():
    assert weather_service._weather_code_label(0) == "Clear sky"
    assert weather_service._weather_code_label(61) == "Rain"
    assert weather_service._weather_code_label(95) == "Thunderstorm"


def test_live_weather_returns_current_hourly_and_daily_forecast(monkeypatch):
    weather_service._cache.clear()
    monkeypatch.setattr(
        weather_service.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(forecast_payload()),
    )

    result = weather_service.get_farm_weather({
        "name": "Musombi Farm",
        "town": "Namarambi",
        "county": "Bungoma",
        "latitude": 0.65,
        "longitude": 34.55,
    })

    assert result["provider"] == "Open-Meteo"
    assert result["current"]["temperature_c"] == 24.2
    assert result["current"]["humidity_percent"] == 68
    assert result["current"]["condition"] == "Rain"
    assert len(result["hourly"]) == 2
    assert result["daily"][0]["rainfall_mm"] == 8.2
    assert result["location"]["latitude"] == 0.65
    assert result["cached"] is False


def test_missing_farm_location_returns_clear_validation_error():
    try:
        weather_service.get_farm_weather({"name": "Unnamed farm"})
    except APIError as exc:
        assert exc.status_code == 422
        assert exc.code == "farm_location_required"
    else:
        raise AssertionError("Expected missing farm location to be rejected")
