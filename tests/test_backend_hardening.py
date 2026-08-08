import math

import pandas as pd
import pytest


def valid_snapshot(app_module):
    row = app_module.LATEST_RECORDS.iloc[0]
    payload = {
        "hospital_id": int(row["hospital_id"]),
        "timestamp": pd.Timestamp(row["timestamp"]).strftime("%Y-%m-%dT%H:%M:%S"),
        "disaster_type": str(row["disaster_type"]),
        "triage_level": str(row["triage_level"]),
        "injury_type": str(row["injury_type"]),
    }
    for name in app_module.NUMERIC_INPUT_COLUMNS:
        payload[name] = float(row[name])
    return payload


def valid_allocation_payload(app_module):
    return {
        "selected_hospital_id": 1,
        "use_current_scenario": False,
        "reserve": {"icu_beds": 12, "ventilators": 8, "staff": 25},
        "weights": {
            "patient_safety": 1,
            "overload_relief": 1,
            "patient_demand": 1,
            "incident_proximity": 1,
        },
    }


def test_preserves_time_split_feature_separation_and_resilience_formula(app_module):
    assert app_module.SPLIT_INFO["shared_timestamps"] == 0
    assert set(app_module.OUTPUT_COLUMNS).isdisjoint(app_module.FEATURE_COLUMNS)

    prediction = {"overload_risk_score": 0.50}
    record = {
        "bed_occupancy_rate": 0.80,
        "icu_occupancy_rate": 0.60,
        "equipment_usage_rate": 0.40,
    }
    resilience = app_module.calculate_resilience_index(prediction, record)
    assert resilience["index"] == 41.5
    assert resilience["status"] == "Severe operational pressure"


def test_preserves_allocation_invariants(app_module):
    scored_rows = [
        {"hospital_id": 1, "priority_score": 80.0, "predicted_icu_beds": 5,
         "predicted_ventilators": 3, "predicted_staff": 8},
        {"hospital_id": 2, "priority_score": 30.0, "predicted_icu_beds": 4,
         "predicted_ventilators": 2, "predicted_staff": 7},
    ]
    reserve = {"icu_beds": 6, "ventilators": 4, "staff": 10}
    plan = app_module.build_allocation_plan(scored_rows, reserve)

    assert plan["total_allocated"]["icu_beds"] <= reserve["icu_beds"]
    assert plan["total_allocated"]["ventilators"] <= reserve["ventilators"]
    assert plan["total_allocated"]["staff"] <= reserve["staff"]
    for row in plan["rows"]:
        assert 0 <= row["icu_allocated"] <= row["predicted_icu_beds"]
        assert 0 <= row["ventilators_allocated"] <= row["predicted_ventilators"]
        assert 0 <= row["staff_allocated"] <= row["predicted_staff"]


@pytest.mark.parametrize("url", ["/api/predict", "/api/allocate", "/api/chat", "/api/briefing"])
@pytest.mark.parametrize("payload", [[], "text", 7, True])
def test_post_routes_reject_non_object_json_with_bounded_400(client, url, payload):
    response = client.post(url, json=payload)
    assert response.status_code == 400
    assert response.is_json
    assert len(response.get_data()) < 1024


@pytest.mark.parametrize("hospital_id", [True, False, 1.5])
def test_snapshot_rejects_boolean_and_fractional_hospital_ids(app_module, client, hospital_id):
    payload = valid_snapshot(app_module)
    payload["hospital_id"] = hospital_id
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("url,payload_builder,id_field", [
    ("/api/allocate", valid_allocation_payload, "selected_hospital_id"),
    ("/api/chat", lambda app: {"message": "status", "selected_hospital_id": 1}, "selected_hospital_id"),
])
@pytest.mark.parametrize("hospital_id", [True, 1.5])
def test_other_routes_reject_boolean_and_fractional_hospital_ids(
    app_module, client, url, payload_builder, id_field, hospital_id
):
    payload = payload_builder(app_module)
    payload[id_field] = hospital_id
    response = client.post(url, json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("field,value", [
    ("doctor_available", 1e100),
    ("doctor_available", math.nan),
    ("incident_distance_km", math.inf),
])
def test_snapshot_rejects_extreme_and_nonfinite_numbers(app_module, client, field, value):
    payload = valid_snapshot(app_module)
    payload[field] = value
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("timestamp", [
    ["2026-01-01T00:00:00"],
    {"value": "2026-01-01T00:00:00"},
    "2026-01-01T00:00:00+03:30",
])
def test_snapshot_rejects_non_scalar_or_timezone_ambiguous_timestamp(
    app_module, client, timestamp
):
    payload = valid_snapshot(app_module)
    payload["timestamp"] = timestamp
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("reserve", [
    {"icu_beds": 1.5, "ventilators": 2, "staff": 3},
    {"icu_beds": True, "ventilators": 2, "staff": 3},
    {"icu_beds": -1, "ventilators": 2, "staff": 3},
    {"icu_beds": 1e100, "ventilators": 2, "staff": 3},
])
def test_reserve_requires_bounded_nonnegative_whole_units(app_module, client, reserve):
    payload = valid_allocation_payload(app_module)
    payload["reserve"] = reserve
    response = client.post("/api/allocate", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("field,value", [
    ("reserve", []),
    ("reserve", "icu_beds"),
    ("weights", []),
    ("weights", "patient_safety"),
    ("use_current_scenario", "false"),
])
def test_allocate_rejects_invalid_nested_types(app_module, client, field, value):
    payload = valid_allocation_payload(app_module)
    payload[field] = value
    response = client.post("/api/allocate", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("weight", [True, -1, 1e100, math.nan])
def test_objective_weights_reject_booleans_negative_and_extreme_values(
    app_module, client, weight
):
    payload = valid_allocation_payload(app_module)
    payload["weights"]["patient_safety"] = weight
    response = client.post("/api/allocate", json=payload)
    assert response.status_code == 400


def test_request_body_limit_returns_json_413(client):
    response = client.post("/api/chat", json={"message": "x" * 200_000})
    assert response.status_code == 413
    assert response.is_json


def test_api_responses_have_security_and_no_store_headers(client):
    response = client.get("/api/status")
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_not_ready_status_is_503_and_hides_internal_error(app_module, client, monkeypatch):
    monkeypatch.setattr(app_module, "MODEL_READY", False)
    monkeypatch.setattr(app_module, "STARTUP_ERROR", "secret-value C:\\private\\dataset.csv")
    response = client.get("/api/status")
    body = response.get_data(as_text=True)
    assert response.status_code == 503
    assert response.get_json()["ready"] is False
    assert "secret-value" not in body
    assert "private" not in body


def test_internal_log_event_does_not_render_exception_message(app_module, capsys):
    app_module.log_internal_event(
        "connection_failed",
        error=ValueError("secret-value https://user:password@example.invalid"),
    )
    output = capsys.readouterr().out
    assert "connection_failed" in output
    assert "ValueError" in output
    assert "secret-value" not in output
    assert "password" not in output


def test_environment_takes_precedence_over_file_values(app_module, monkeypatch):
    monkeypatch.setenv("AIONEX_TEST_SETTING", "from-environment")
    assert app_module.get_live_setting(
        {"AIONEX_TEST_SETTING": "from-file"},
        "AIONEX_TEST_SETTING",
        "default",
    ) == "from-environment"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://api.openai.com/v1",
    "https://user:password@api.openai.com/v1",
    "https://api.openai.com.evil.example/v1",
    "https://169.254.169.254/latest/meta-data",
    "https://api.openai.com/v1?token=value",
])
def test_ai_endpoint_validation_rejects_unsafe_urls(app_module, url):
    normalized, error = app_module.validate_ai_base_url(url, {"api.openai.com"})
    assert normalized == ""
    assert error


@pytest.mark.parametrize("url", [
    "https://api.openai.com/v1",
    "http://127.0.0.1:11434/v1",
    "http://localhost:11434/v1",
])
def test_ai_endpoint_validation_accepts_allowlisted_https_and_loopback(app_module, url):
    normalized, error = app_module.validate_ai_base_url(url, {"api.openai.com"})
    assert normalized
    assert error == ""


def test_ai_redirect_handler_never_follows_redirects(app_module):
    handler = app_module.NoRedirectHandler()
    assert handler.redirect_request(None, None, 302, "redirect", {}, "https://evil.example") is None


def test_ai_response_reader_enforces_declared_and_streamed_size(app_module):
    class FakeResponse:
        def __init__(self, content_length, body):
            self.headers = {"Content-Length": content_length} if content_length is not None else {}
            self.body = body

        def read(self, size):
            return self.body[:size]

    too_large = app_module.MAX_AI_RESPONSE_BYTES + 1
    with pytest.raises(app_module.AIResponseTooLargeError):
        app_module.read_limited_ai_response(FakeResponse(str(too_large), b"{}"))
    with pytest.raises(app_module.AIResponseTooLargeError):
        app_module.read_limited_ai_response(FakeResponse(None, b"x" * too_large))


def test_invalid_ai_numeric_settings_are_bounded_without_throwing(app_module, monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "nan")
    monkeypatch.setenv("AI_MAX_TOKENS", "-9")
    monkeypatch.setenv("AI_TEMPERATURE", "999")
    settings = app_module.get_ai_settings()
    assert settings["configuration_error"]
    assert 1 <= settings["timeout_seconds"] <= 60
    assert 1 <= settings["max_tokens"] <= 4096
    assert 0 <= settings["temperature"] <= 2


@pytest.mark.parametrize("answer", ["[]", '[{"summary": "hidden"}]', '"text"', "1", "null"])
def test_non_object_briefing_json_uses_fallback_parser_result(app_module, answer):
    assert app_module.read_briefing_json(answer) == ("", [])


def test_ai_briefing_falls_back_on_non_object_json(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "get_ai_settings", lambda: {
        "enabled": True,
        "model": "test-model",
        "configuration_error": "",
    })
    monkeypatch.setattr(app_module, "call_language_model", lambda *_: ("[]", ""))

    cards = {
        "patients_next_2h": {"value": 10, "low": 8, "high": 12},
        "icu_beds": {"value": 3, "low": 2, "high": 4},
        "ventilators": {"value": 2, "low": 1, "high": 3},
        "staff": {"value": 7, "low": 6, "high": 8},
        "overload_risk": {"value": 55.0},
    }
    capacity = {"status": "Warning", "confidence_percent": 70.0}
    resilience = {"index": 50.0, "status": "Pressured but manageable"}
    record = valid_snapshot(app_module)
    strategies = {
        "immediate_priorities": ["Review surge capacity."],
        "next_two_hours": ["Prepare resources."],
        "monitoring_priorities": [],
        "coordination_options": [],
    }

    result = app_module.build_ai_briefing(
        cards, capacity, resilience, record, [], {"count": 0}, strategies
    )
    assert result["ai_used"] is False
    assert result["summary"]
    assert result["ai_error"]


def test_clean_dataset_drops_invalid_targets_labels_and_fractional_ids(app_module):
    base = app_module.CLEAN_DATA.iloc[0].copy()
    rows = []
    for offset in range(4):
        row = base.copy()
        row["timestamp"] = pd.Timestamp(base["timestamp"]) + pd.Timedelta(hours=100 + offset)
        rows.append(row)

    rows[1]["required_staff"] = "not-a-number"
    rows[2][app_module.CLASSIFICATION_TARGET] = "Unexpected"
    rows[3]["hospital_id"] = 1.5

    cleaned = app_module.clean_dataset(pd.DataFrame(rows))
    assert len(cleaned) == 1
    assert cleaned.iloc[0][app_module.CLASSIFICATION_TARGET] in app_module.STATUS_ORDER


def test_server_defaults_to_loopback_and_disables_public_debug(app_module, monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    assert app_module.get_host_address() == "127.0.0.1"

    monkeypatch.setenv("DEBUG", "true")
    assert app_module.get_safe_debug_flag("127.0.0.1") is True
    assert app_module.get_safe_debug_flag("0.0.0.0") is False


def test_unknown_hospital_reply_lists_configured_noncontiguous_ids(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "DATASET_INFO", {"hospital_count": 2})
    monkeypatch.setattr(app_module, "CATEGORY_OPTIONS", {
        "hospitals": [
            {"id": 4, "label": "Hospital 4"},
            {"id": 19, "label": "Hospital 19"},
        ],
    })

    reply = app_module.answer_unknown_hospital(7)

    assert "Available identifiers: 4, 19." in reply["details"]
    assert "numbered 1 to" not in " ".join(reply["details"])
    assert "predict hospital 4" in " ".join(reply["details"])


def test_model_reply_summarizes_current_metric_values(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "REGRESSION_METRICS", [
        {"label": "Target A", "r2": -0.25, "mae": 2.0, "unit": "units"},
        {"label": "Target B", "r2": 0.875, "mae": 1.0, "unit": "units"},
    ])
    monkeypatch.setattr(app_module, "CLASSIFICATION_METRICS", {
        "accuracy": 0.625,
        "macro_f1": 0.51,
    })

    reply = app_module.answer_about_model()

    assert "range from -0.25 to 0.875 across 2 targets" in reply["answer"]
    assert "62.5% accuracy and macro F1 0.51" in reply["answer"]
    assert "near 0.5" not in reply["answer"]


def test_pressure_ranking_reply_handles_one_hospital(app_module, monkeypatch):
    only_row = {
        "hospital_label": "Hospital 41",
        "priority_score": 72.0,
        "capacity_status": "Warning",
        "overload_risk_percent": 63.0,
    }
    monkeypatch.setattr(app_module, "rank_hospitals_by_pressure", lambda: [only_row])

    reply = app_module.answer_about_pressure_ranking()

    assert len(reply["details"]) == 2
    assert "Hospital 41 has the highest modeled pressure" in reply["answer"]
    assert reply["source_note"] == "Source: model predictions for 1 latest dataset record."
