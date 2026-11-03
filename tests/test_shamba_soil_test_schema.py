from __future__ import annotations

import pytest

from backend.jumuiya.shamba import schemas


def test_soil_test_schema_accepts_calibrated_meter_reading():
    payload = schemas.soil_test_payload({
        "method": "digital_meter",
        "measured_ph": 6.4,
        "calibration_status": "calibrated",
        "calibration_date": "2026-11-03",
        "sample_depth_cm": 15,
        "sample_location": "North field",
    })

    assert payload["method"] == "digital_meter"
    assert payload["measured_ph"] == 6.4
    assert payload["calibration_status"] == "calibrated"
    assert payload["sample_depth_cm"] == 15.0


def test_soil_test_schema_allows_visual_estimate_without_measured_ph():
    payload = schemas.soil_test_payload({
        "method": "test_strip",
        "measured_ph": None,
        "ai_visual_estimate": "Colour appears closest to the pH 6 chart swatch.",
        "ai_assessment": "Preliminary visual estimate only.",
    })

    assert payload["measured_ph"] is None
    assert payload["ai_visual_estimate"]
    assert payload["method"] == "test_strip"


@pytest.mark.parametrize("value", [-0.1, 14.1, "not-a-number"])
def test_soil_test_schema_rejects_invalid_ph(value):
    with pytest.raises(ValueError):
        schemas.soil_test_payload({
            "method": "digital_meter",
            "measured_ph": value,
            "calibration_status": "calibrated",
        })


def test_soil_test_schema_rejects_unsupported_method():
    with pytest.raises(ValueError, match="method must be"):
        schemas.soil_test_payload({"method": "camera_only"})


def test_soil_test_schema_rejects_unsupported_calibration_status():
    with pytest.raises(ValueError, match="calibration_status is not supported"):
        schemas.soil_test_payload({
            "method": "digital_meter",
            "measured_ph": 6.5,
            "calibration_status": "pretend_calibrated",
        })
