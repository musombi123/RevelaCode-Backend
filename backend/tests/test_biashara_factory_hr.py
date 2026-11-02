from __future__ import annotations

from datetime import time

import pytest

from backend.jumuiya.biashara import factory, hr
from backend.jumuiya.core.errors import APIError


def test_factory_batch_requires_explicit_raw_and_finished_sku_types():
    raw = {"production_type": "raw_material", "unit": "kg"}
    finished = {"production_type": "finished_good", "unit": "kg"}

    assert factory._validate_material_pair(raw, finished, 100, 95) == "kg"

    with pytest.raises(APIError) as error:
        factory._validate_material_pair({"production_type": "resale", "unit": "kg"}, finished, 100, 95)
    assert error.value.code == "invalid_raw_material_type"

    with pytest.raises(APIError) as error:
        factory._validate_material_pair(raw, {"production_type": "resale", "unit": "kg"}, 100, 95)
    assert error.value.code == "invalid_finished_good_type"


def test_factory_batch_rejects_mixed_units_and_impossible_expected_output():
    raw = {"production_type": "raw_material", "unit": "kg"}
    finished = {"production_type": "finished_good", "unit": "bag"}

    with pytest.raises(APIError) as error:
        factory._validate_material_pair(raw, finished, 100, 95)
    assert error.value.code == "production_unit_mismatch"

    with pytest.raises(APIError) as error:
        factory._validate_material_pair(
            {"production_type": "raw_material", "unit": "kg"},
            {"production_type": "finished_good", "unit": "kg"},
            100,
            101,
        )
    assert error.value.code == "invalid_expected_yield"


def test_factory_quantity_validation_rejects_zero_input_but_allows_zero_wastage():
    assert factory._decimal("0", "wastage", allow_zero=True) == 0

    with pytest.raises(APIError):
        factory._decimal("0", "input_quantity")


def test_hr_gps_is_optional_and_validates_coordinates():
    assert hr._gps({}) is None
    assert hr._gps({"latitude": -1.28, "longitude": 36.82, "accuracy_meters": 12}) == {
        "latitude": -1.28,
        "longitude": 36.82,
        "accuracy_meters": 12.0,
    }

    with pytest.raises(APIError) as error:
        hr._gps({"latitude": 100, "longitude": 36.82})
    assert error.value.code == "invalid_gps"


def test_hr_shift_time_uses_24_hour_clock():
    assert hr._shift_time("08:30", "shift_start", "08:00") == time(8, 30)

    with pytest.raises(APIError):
        hr._shift_time("8:30 AM", "shift_start", "08:00")
