"""Happy-path API contracts for the browser workflows."""

import pandas as pd


def snapshot_from_latest_record(app_module):
    """Return a complete browser-shaped snapshot from one configured record."""
    row = app_module.LATEST_RECORDS.iloc[0]
    snapshot = {
        "hospital_id": int(row["hospital_id"]),
        "timestamp": pd.Timestamp(row["timestamp"]).strftime("%Y-%m-%dT%H:%M:%S"),
        "disaster_type": str(row["disaster_type"]),
        "triage_level": str(row["triage_level"]),
        "injury_type": str(row["injury_type"]),
    }
    for column_name in app_module.NUMERIC_INPUT_COLUMNS:
        snapshot[column_name] = float(row[column_name])
    return snapshot


def test_bootstrap_contracts_are_ready_and_self_contained(client):
    status_response = client.get("/api/status")
    options_response = client.get("/api/options")

    assert status_response.status_code == 200
    status = status_response.get_json()
    assert status["ready"] is True
    assert status["dataset"]["row_count"] > 0
    assert status["dataset"]["hospital_count"] == 3
    assert set(status["ai"]) >= {"enabled", "available", "configuration_valid"}
    assert "https://cdn.jsdelivr.net" not in status_response.headers["Content-Security-Policy"]

    assert options_response.status_code == 200
    options = options_response.get_json()
    assert len(options["hospitals"]) == status["dataset"]["hospital_count"]
    assert options["disaster_types"]
    assert options["triage_levels"]
    assert options["injury_types"]


def test_latest_history_and_prediction_contracts(app_module, client):
    snapshot = snapshot_from_latest_record(app_module)
    hospital_id = snapshot["hospital_id"]

    latest_response = client.get(f"/api/hospital/{hospital_id}/latest")
    assert latest_response.status_code == 200
    latest = latest_response.get_json()
    assert latest["hospital_id"] == hospital_id
    assert latest["record_label"] == "Latest dataset record"

    history_response = client.get(f"/api/history/{hospital_id}")
    assert history_response.status_code == 200
    history = history_response.get_json()
    assert history["hospital_id"] == hospital_id
    assert len(history["weekly_labels"]) == len(history["weekly_values"]["overload_risk_percent"])
    assert set(history["trends"]) == {"overload_risk", "bed_occupancy", "icu_occupancy"}

    prediction_response = client.post("/api/predict", json=snapshot)
    assert prediction_response.status_code == 200
    prediction = prediction_response.get_json()
    assert prediction["hospital_id"] == hospital_id
    assert set(prediction["predictions"]) == {
        "patients_next_2h",
        "icu_beds",
        "staff",
        "ventilators",
        "overload_risk",
    }
    assert prediction["capacity"]["status"] in {"Stable", "Warning", "High Risk"}
    assert 0 <= prediction["resilience"]["index"] <= 100
    assert set(prediction["recovery_strategies"]) == {
        "coordination_options",
        "immediate_priorities",
        "monitoring_priorities",
        "next_two_hours",
    }


def test_allocation_chat_and_briefing_contracts(app_module, client):
    snapshot = snapshot_from_latest_record(app_module)
    hospital_id = snapshot["hospital_id"]
    allocation_payload = {
        "selected_hospital_id": hospital_id,
        "use_current_scenario": True,
        "snapshot": snapshot,
        "reserve": {"icu_beds": 12, "ventilators": 8, "staff": 25},
        "weights": {
            "patient_safety": 1,
            "overload_relief": 1,
            "patient_demand": 1,
            "incident_proximity": 1,
        },
    }

    allocation_response = client.post("/api/allocate", json=allocation_payload)
    assert allocation_response.status_code == 200
    allocation = allocation_response.get_json()
    assert allocation["selected_hospital_id"] == hospital_id
    assert allocation["used_current_scenario"] is True
    assert allocation["hospital_count"] == 3
    assert len(allocation["rows"]) == allocation["hospital_count"]
    for resource_name in ("icu_beds", "ventilators", "staff"):
        assert allocation["total_allocated"][resource_name] <= allocation["reserve_entered"][resource_name]

    chat_response = client.post(
        "/api/chat",
        json={"message": "Summarize the dataset", "selected_hospital_id": hospital_id},
    )
    assert chat_response.status_code == 200
    chat = chat_response.get_json()
    assert isinstance(chat["answer"], str) and chat["answer"]
    assert isinstance(chat["details"], list)
    assert chat["ai_used"] is False

    briefing_response = client.post("/api/briefing", json=snapshot)
    assert briefing_response.status_code == 200
    briefing = briefing_response.get_json()
    assert briefing["hospital_label"]
    assert isinstance(briefing["summary"], str) and briefing["summary"]
    assert isinstance(briefing["recommendations"], list)
    assert briefing["ai_used"] is False
