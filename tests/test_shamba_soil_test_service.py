from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from bson import ObjectId

from backend.jumuiya.shamba import services


class FakeFarmCollection:
    def __init__(self, farm):
        self.farm = deepcopy(farm)
        self.updates = []

    def find_one(self, query, **kwargs):
        return deepcopy(self.farm)

    def update_one(self, query, update, **kwargs):
        self.updates.append(deepcopy(update))
        self.farm.update(update.get("$set", {}))
        return SimpleNamespace(modified_count=1)


class FakeSoilTestCollection:
    def __init__(self):
        self.document = None
        self.inserted_id = ObjectId()

    def insert_one(self, document):
        self.document = deepcopy(document)
        self.document["_id"] = self.inserted_id
        return SimpleNamespace(inserted_id=self.inserted_id)

    def find_one(self, query, **kwargs):
        if self.document and query.get("_id") == self.inserted_id:
            return deepcopy(self.document)
        return None


def run_create_soil_test(monkeypatch, method, measured_ph, calibration_status):
    farm_id = ObjectId()
    farm_collection = FakeFarmCollection({
        "_id": farm_id,
        "owner_user_id": "farmer-user",
        "status": "active",
        "soil_ph": 6.0,
    })
    test_collection = FakeSoilTestCollection()

    def get_collection(name):
        if name == services.FARMS:
            return farm_collection
        if name == services.SOIL_TESTS:
            return test_collection
        raise AssertionError(f"Unexpected collection requested: {name}")

    monkeypatch.setattr(services, "_collection", get_collection)
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)

    result = services.create_soil_test(
        "farmer-user",
        str(farm_id),
        {
            "method": method,
            "measured_ph": measured_ph,
            "calibration_status": calibration_status,
            "ai_visual_estimate": "Visible colour appears near pH 6." if measured_ph is None else "",
        },
    )
    return result, farm_collection


def test_uncalibrated_digital_meter_reading_is_saved_but_not_trusted(monkeypatch):
    result, farm = run_create_soil_test(
        monkeypatch,
        method="digital_meter",
        measured_ph=6.3,
        calibration_status="uncalibrated",
    )

    assert result["measurement_status"] == "uncalibrated_reading"
    assert result["measured_ph"] == 6.3
    assert farm.updates == []
    assert farm.farm["soil_ph"] == 6.0


def test_calibrated_digital_meter_updates_authoritative_farm_ph(monkeypatch):
    result, farm = run_create_soil_test(
        monkeypatch,
        method="digital_meter",
        measured_ph=6.5,
        calibration_status="calibrated",
    )

    assert result["measurement_status"] == "measured"
    assert farm.farm["soil_ph"] == 6.5
    assert len(farm.updates) == 1


def test_numeric_test_strip_result_updates_farm_ph_without_meter_calibration(monkeypatch):
    result, farm = run_create_soil_test(
        monkeypatch,
        method="test_strip",
        measured_ph=5.8,
        calibration_status="not_applicable",
    )

    assert result["measurement_status"] == "measured"
    assert farm.farm["soil_ph"] == 5.8
    assert len(farm.updates) == 1


def test_ai_visual_estimate_never_overwrites_measured_farm_ph(monkeypatch):
    result, farm = run_create_soil_test(
        monkeypatch,
        method="test_strip",
        measured_ph=None,
        calibration_status="not_applicable",
    )

    assert result["measurement_status"] == "visual_estimate_only"
    assert result["ai_visual_estimate"]
    assert farm.updates == []
    assert farm.farm["soil_ph"] == 6.0
