import csv
import importlib
import os
import sys
from datetime import datetime, timedelta

import pytest

FIELDNAMES = [
    "hospital_id",
    "timestamp",
    "disaster_type",
    "incident_distance_km",
    "ambulance_arrivals_per_hour",
    "patient_arrival_rate",
    "triage_level",
    "injury_type",
    "avg_treatment_time_min",
    "mortality_risk_score",
    "bed_occupancy_rate",
    "icu_occupancy_rate",
    "equipment_usage_rate",
    "nurse_to_patient_ratio",
    "doctor_available",
    "predicted_patients_next_2h",
    "required_icu_beds",
    "required_ventilators",
    "required_staff",
    "overload_risk_score",
    "capacity_flag",
]


def write_test_dataset(path):
    statuses = ["Stable", "Warning", "High Risk"]
    disasters = ["Flood", "Earthquake", "Fire"]
    triage_levels = ["Low", "Medium", "High"]
    injuries = ["Minor", "Moderate", "Severe"]
    start = datetime(2026, 1, 1, 0, 0)

    rows = []
    for hour_index in range(30):
        for hospital_id in range(1, 4):
            pressure = ((hour_index + hospital_id) % 10) / 20.0
            rows.append({
                "hospital_id": hospital_id,
                "timestamp": (start + timedelta(hours=hour_index)).isoformat(timespec="minutes"),
                "disaster_type": disasters[(hour_index + hospital_id) % len(disasters)],
                "incident_distance_km": 5.0 + hospital_id + (hour_index / 10.0),
                "ambulance_arrivals_per_hour": 2.0 + hospital_id + (hour_index % 5),
                "patient_arrival_rate": 8.0 + hospital_id + (hour_index % 7),
                "triage_level": triage_levels[(hour_index + hospital_id) % len(triage_levels)],
                "injury_type": injuries[(hour_index + hospital_id) % len(injuries)],
                "avg_treatment_time_min": 20.0 + hour_index,
                "mortality_risk_score": min(0.95, 0.05 + pressure),
                "bed_occupancy_rate": min(0.98, 0.40 + pressure),
                "icu_occupancy_rate": min(0.98, 0.35 + pressure),
                "equipment_usage_rate": min(0.98, 0.30 + pressure),
                "nurse_to_patient_ratio": 0.15 + (hospital_id / 100.0),
                "doctor_available": 5.0 + hospital_id,
                "predicted_patients_next_2h": 15.0 + hour_index + hospital_id,
                "required_icu_beds": 2.0 + hospital_id + (hour_index % 3),
                "required_ventilators": 1.0 + (hour_index % 4),
                "required_staff": 8.0 + hospital_id + (hour_index % 5),
                "overload_risk_score": min(0.98, 0.20 + pressure),
                "capacity_flag": statuses[(hour_index + hospital_id) % len(statuses)],
            })

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    dataset_path = tmp_path_factory.mktemp("backend-data") / "fixture.csv"
    write_test_dataset(dataset_path)

    os.environ["DATASET_PATH"] = str(dataset_path)
    os.environ["AI_ENABLED"] = "false"
    os.environ["AI_API_KEY"] = ""
    os.environ["AI_BASE_URL"] = "https://api.openai.com/v1"
    os.environ["AI_ALLOWED_HOSTS"] = "api.openai.com"
    os.environ["AI_TIMEOUT_SECONDS"] = "5"
    os.environ["AI_MAX_TOKENS"] = "200"
    os.environ["AI_TEMPERATURE"] = "0.2"
    os.environ["DEBUG"] = "false"
    os.environ["HOST"] = "127.0.0.1"

    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    assert module.MODEL_READY, module.STARTUP_ERROR
    return module


@pytest.fixture()
def client(app_module):
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()
