# Install dependencies:
# pip install flask pandas numpy scikit-learn

# =============================================================================
# SECTION 1: IMPORTS AND BASIC SETTINGS
# This section only imports libraries and defines basic paths.
# It does not read the dataset, does not clean data and does not train models.
# =============================================================================

import ipaddress
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    r2_score,
)

# Folder that contains this file. Relative dataset paths are resolved from here.
APP_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Path of the small .env configuration file that sits next to app.py.
ENV_FILE_PATH = os.path.join(APP_FOLDER, ".env")

# Global flags that describe whether the machine-learning part is usable.
MODEL_READY = False
STARTUP_ERROR = ""

# Global places where the loaded data, the trained models and the metrics live.
CLEAN_DATA = None
TRAIN_DATA = None
TEST_DATA = None
LATEST_RECORDS = None
FEATURE_COLUMNS = []
REGRESSION_MODEL = None
CLASSIFICATION_MODEL = None
REGRESSION_METRICS = []
CLASSIFICATION_METRICS = {}
FEATURE_IMPORTANCES = []
SPLIT_INFO = {}
DATASET_INFO = {}
TRAINING_RANGES = {}
CATEGORY_OPTIONS = {}

# Wording used everywhere so the interface never calls these models "deep learning".
METHODOLOGY_LABEL = "Tree-based machine-learning models for structured crisis data."
ALLOCATION_METHOD_LABEL = "Transparent priority-based constrained allocation"

# Threshold used to decide whether a weekly dataset trend is worsening or improving.
# The value is a change of the rate (0-1 scale) per week.
TREND_SLOPE_THRESHOLD = 0.002

# Defensive limits for the small JSON requests served by this application.
MAX_REQUEST_BODY_BYTES = 128 * 1024
MAX_AI_RESPONSE_BYTES = 256 * 1024
MAX_OPERATIONAL_NUMBER = 1_000_000.0
MAX_RESERVE_UNITS = 1_000_000
MAX_OBJECTIVE_WEIGHT = 1_000_000.0
PUBLIC_STARTUP_ERROR = "The service could not initialize. Check the server logs."

# Broad operational maxima prevent float overflows and accidental resource
# exhaustion while still allowing values far beyond the configured dataset.
NUMERIC_INPUT_MAXIMUMS = {
    "incident_distance_km": MAX_OPERATIONAL_NUMBER,
    "ambulance_arrivals_per_hour": MAX_OPERATIONAL_NUMBER,
    "patient_arrival_rate": MAX_OPERATIONAL_NUMBER,
    "avg_treatment_time_min": MAX_OPERATIONAL_NUMBER,
    "mortality_risk_score": 1.0,
    "bed_occupancy_rate": 1.0,
    "icu_occupancy_rate": 1.0,
    "equipment_usage_rate": 1.0,
    "nurse_to_patient_ratio": MAX_OPERATIONAL_NUMBER,
    "doctor_available": MAX_OPERATIONAL_NUMBER,
}


# =============================================================================
# SECTION 2: READ THE .ENV FILE
# This section reads simple NAME=VALUE settings from the .env file.
# It does not use python-dotenv and it never prints secret values.
# =============================================================================

def read_env_file(env_path):
    """Read simple NAME=VALUE lines from a .env file and add them to os.environ."""
    if not os.path.exists(env_path):
        return False

    with open(env_path, encoding="utf-8") as env_file:
        all_lines = env_file.readlines()

    for raw_line in all_lines:
        line = raw_line.strip()

        # Skip blank lines and comment lines.
        if line == "":
            continue
        if line.startswith("#"):
            continue
        if "=" not in line:
            continue

        name_part, value_part = line.split("=", 1)
        name = name_part.strip()
        value = value_part.strip()

        # Do not overwrite a variable that the operating system already provides.
        if name != "" and name not in os.environ:
            os.environ[name] = value

    return True


def get_setting(name, default_value):
    """Return one setting from the environment, or a default value."""
    value = os.environ.get(name, default_value)
    if value is None:
        return default_value
    return str(value).strip()


def get_dataset_path():
    """Return the absolute dataset path built from DATASET_PATH in the .env file."""
    raw_path = get_setting("DATASET_PATH", "")
    if raw_path == "":
        return ""
    if os.path.isabs(raw_path):
        return raw_path
    # A relative path is resolved against the folder that contains app.py.
    return os.path.normpath(os.path.join(APP_FOLDER, raw_path))


def get_port_number():
    """Return the server port from the .env file, or 5000 when it is not valid."""
    raw_port = get_setting("PORT", "5000")
    try:
        port_number = int(raw_port)
    except ValueError:
        return 5000
    if port_number < 1 or port_number > 65535:
        return 5000
    return port_number


def get_host_address():
    """Return a conservative server bind address, defaulting to loopback."""
    raw_host = get_setting("HOST", "127.0.0.1")
    if raw_host == "" or len(raw_host) > 255:
        return "127.0.0.1"
    if any(character.isspace() for character in raw_host):
        return "127.0.0.1"
    if "/" in raw_host or "\\" in raw_host or "://" in raw_host:
        return "127.0.0.1"
    if not all(character.isalnum() or character in (".", "-", ":", "[", "]") for character in raw_host):
        return "127.0.0.1"
    return raw_host


def is_loopback_host(host_name):
    """Return True only for localhost or a numeric loopback address."""
    candidate = str(host_name).strip().lower()
    if candidate == "localhost":
        return True
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def get_debug_flag():
    """Return True only when DEBUG is clearly switched on in the .env file."""
    raw_debug = get_setting("DEBUG", "false").lower()
    if raw_debug in ["true", "1", "yes", "on"]:
        return True
    return False


def get_safe_debug_flag(host_name):
    """Allow Flask debug mode only when the server is bound to loopback."""
    debug_requested = get_debug_flag()
    if debug_requested and not is_loopback_host(host_name):
        log_internal_event("debug_disabled_for_non_loopback_bind")
        return False
    return debug_requested


def get_flag(name, default_text):
    """Read a simple true or false setting from the environment."""
    raw_value = get_setting(name, default_text).lower()
    if raw_value in ["true", "1", "yes", "on"]:
        return True
    return False


def get_number_setting(name, default_number):
    """Read a numeric setting and fall back to the default when it is not valid."""
    raw_value = get_setting(name, str(default_number))
    try:
        return float(raw_value)
    except ValueError:
        return float(default_number)


def read_env_values(env_path):
    """Read the .env file again and return its NAME=VALUE pairs as a dictionary."""
    values = {}
    if not os.path.exists(env_path):
        return values

    try:
        with open(env_path, encoding="utf-8") as env_file:
            all_lines = env_file.readlines()
    except OSError:
        return values

    for raw_line in all_lines:
        line = raw_line.strip()
        if line == "" or line.startswith("#") or "=" not in line:
            continue
        name_part, value_part = line.split("=", 1)
        values[name_part.strip()] = value_part.strip()

    return values


def get_live_setting(file_values, name, default_value):
    """Prefer an OS-provided value, then a file value, then the default."""
    if name in os.environ:
        return str(os.environ[name]).strip()
    if name in file_values:
        return str(file_values[name]).strip()
    return str(default_value).strip()


def read_ai_allowed_hosts():
    """Return the exact public hostnames permitted for AI egress."""
    raw_value = get_setting("AI_ALLOWED_HOSTS", "api.openai.com")
    hosts = set()
    for item in raw_value.split(",")[:32]:
        host_name = item.strip().lower().rstrip(".")
        if host_name != "" and len(host_name) <= 253:
            hosts.add(host_name)
    return hosts


def validate_ai_base_url(raw_url, allowed_hosts):
    """Validate and normalize an AI endpoint without performing DNS or network I/O."""
    candidate = str(raw_url).strip()
    if candidate == "" or len(candidate) > 2048:
        return "", "AI_BASE_URL is empty or too long."
    if any(ord(character) < 33 or ord(character) == 127 for character in candidate):
        return "", "AI_BASE_URL contains unsupported characters."

    try:
        parsed = urllib.parse.urlsplit(candidate)
        port_number = parsed.port
    except (TypeError, ValueError):
        return "", "AI_BASE_URL is not a valid URL."

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return "", "AI_BASE_URL must use HTTP or HTTPS."
    if parsed.username is not None or parsed.password is not None:
        return "", "AI_BASE_URL must not contain user credentials."
    if parsed.query != "" or parsed.fragment != "":
        return "", "AI_BASE_URL must not contain a query string or fragment."
    if parsed.hostname is None:
        return "", "AI_BASE_URL must contain a hostname."

    host_name = parsed.hostname.lower().rstrip(".")
    loopback = is_loopback_host(host_name)
    if scheme == "http" and not loopback:
        return "", "Non-loopback AI endpoints must use HTTPS."
    if not loopback and host_name not in allowed_hosts:
        return "", "The AI endpoint hostname is not allowlisted."

    if ":" in host_name:
        normalized_host = "[" + host_name + "]"
    else:
        normalized_host = host_name
    if port_number is not None:
        normalized_host = normalized_host + ":" + str(port_number)

    normalized_path = parsed.path.rstrip("/")
    normalized = urllib.parse.urlunsplit((scheme, normalized_host, normalized_path, "", ""))
    return normalized, ""


def read_bounded_ai_number(name, default_number, minimum, maximum, integer_value=False):
    """Read a finite, bounded numeric AI setting and return a safe fallback on error."""
    raw_value = get_setting(name, str(default_number))
    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return default_number, name + " must be numeric."

    if not math.isfinite(number) or number < minimum or number > maximum:
        return default_number, name + " is outside the allowed range."
    if integer_value and not number.is_integer():
        return default_number, name + " must be a whole number."

    if integer_value:
        return int(number), ""
    return float(number), ""


def get_ai_settings():
    """Read and validate optional language-model settings with OS precedence."""
    settings = {}
    settings["enabled"] = get_flag("AI_ENABLED", "false")

    allowed_hosts = read_ai_allowed_hosts()
    base_url, base_url_error = validate_ai_base_url(
        get_setting("AI_BASE_URL", "https://api.openai.com/v1"),
        allowed_hosts,
    )
    settings["base_url"] = base_url

    model_name = get_setting("AI_MODEL", "gpt-4o-mini")
    model_error = ""
    if model_name == "" or len(model_name) > 200:
        model_name = "gpt-4o-mini"
        model_error = "AI_MODEL is empty or too long."
    settings["model"] = model_name

    api_key = get_setting("AI_API_KEY", "")
    key_error = ""
    if len(api_key) > 4096:
        api_key = ""
        key_error = "AI_API_KEY is too long."
    if any(ord(character) < 32 or ord(character) == 127 for character in api_key):
        api_key = ""
        key_error = "AI_API_KEY contains unsupported characters."
    if api_key != "" and base_url.startswith("http://"):
        key_error = "AI_API_KEY cannot be sent over HTTP."
    settings["api_key"] = api_key

    timeout_value, timeout_error = read_bounded_ai_number(
        "AI_TIMEOUT_SECONDS", 30.0, 1.0, 60.0
    )
    token_value, token_error = read_bounded_ai_number(
        "AI_MAX_TOKENS", 700, 1, 4096, integer_value=True
    )
    temperature_value, temperature_error = read_bounded_ai_number(
        "AI_TEMPERATURE", 0.2, 0.0, 2.0
    )
    settings["timeout_seconds"] = timeout_value
    settings["max_tokens"] = token_value
    settings["temperature"] = temperature_value

    errors = [
        error_text for error_text in [
            base_url_error,
            model_error,
            key_error,
            timeout_error,
            token_error,
            temperature_error,
        ] if error_text != ""
    ]
    settings["configuration_error"] = (
        "The AI configuration is invalid. Check the server logs." if errors else ""
    )
    settings["configuration_issues"] = errors
    return settings


def read_setting_number(file_values, name, default_number):
    """Read one finite numeric setting and fall back to the default when invalid."""
    raw_value = get_live_setting(file_values, name, str(default_number))
    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return float(default_number)
    if not math.isfinite(number):
        return float(default_number)
    return number


# Read the configuration immediately so the rest of the file can use it.
read_env_file(ENV_FILE_PATH)


# =============================================================================
# SECTION 3: DATASET COLUMN DEFINITIONS
# This section only lists the column names and the friendly labels used later.
# It does not read the file and does not change any data.
# =============================================================================

# Columns that describe the current situation. Only these may become model inputs.
NUMERIC_INPUT_COLUMNS = [
    "incident_distance_km",
    "ambulance_arrivals_per_hour",
    "patient_arrival_rate",
    "avg_treatment_time_min",
    "mortality_risk_score",
    "bed_occupancy_rate",
    "icu_occupancy_rate",
    "equipment_usage_rate",
    "nurse_to_patient_ratio",
    "doctor_available",
]

# Original categorical columns from the CSV file.
RAW_CATEGORICAL_COLUMNS = [
    "hospital_id",
    "disaster_type",
    "triage_level",
    "injury_type",
]

# Categorical columns used for encoding. hospital_id becomes text because it is an
# identifier and not a continuous measurement.
CATEGORICAL_FEATURE_COLUMNS = [
    "hospital_id_text",
    "disaster_type",
    "triage_level",
    "injury_type",
]

# Time features created from the timestamp column.
TIME_FEATURE_COLUMNS = ["year", "month", "day", "hour", "day_of_week"]

# The five continuous prediction targets.
REGRESSION_TARGETS = [
    "predicted_patients_next_2h",
    "required_icu_beds",
    "required_ventilators",
    "required_staff",
    "overload_risk_score",
]

# The single classification target.
CLASSIFICATION_TARGET = "capacity_flag"

# All output columns. None of them may ever appear inside the model input matrix.
OUTPUT_COLUMNS = REGRESSION_TARGETS + [CLASSIFICATION_TARGET]

# Every column that the CSV file must contain.
REQUIRED_COLUMNS = [
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

# Rate columns that must stay between 0 and 1.
RATE_COLUMNS = [
    "mortality_risk_score",
    "bed_occupancy_rate",
    "icu_occupancy_rate",
    "equipment_usage_rate",
    "overload_risk_score",
]

# Columns that are shown as a percentage in the interface.
PERCENT_INPUT_COLUMNS = [
    "mortality_risk_score",
    "bed_occupancy_rate",
    "icu_occupancy_rate",
    "equipment_usage_rate",
]

# Numeric fields used to compare a situation with configured dataset records.
SIMILARITY_COLUMNS = [
    "incident_distance_km",
    "ambulance_arrivals_per_hour",
    "patient_arrival_rate",
    "avg_treatment_time_min",
    "mortality_risk_score",
    "bed_occupancy_rate",
    "icu_occupancy_rate",
    "equipment_usage_rate",
    "nurse_to_patient_ratio",
    "doctor_available",
]

# Friendly names used in the interface instead of raw column names.
TARGET_LABELS = {
    "predicted_patients_next_2h": "Patients next 2 hours",
    "required_icu_beds": "ICU beds",
    "required_ventilators": "Ventilators",
    "required_staff": "Staff",
    "overload_risk_score": "Overload risk",
}

TARGET_UNITS = {
    "predicted_patients_next_2h": "patients",
    "required_icu_beds": "beds",
    "required_ventilators": "ventilators",
    "required_staff": "staff units",
    "overload_risk_score": "risk score (0-1)",
}

FEATURE_LABELS = {
    "incident_distance_km": "Distance from incident (km)",
    "ambulance_arrivals_per_hour": "Ambulance arrivals per hour",
    "patient_arrival_rate": "Patient arrival rate",
    "avg_treatment_time_min": "Average treatment time (minutes)",
    "mortality_risk_score": "Mortality risk",
    "bed_occupancy_rate": "Bed occupancy",
    "icu_occupancy_rate": "ICU occupancy",
    "equipment_usage_rate": "Equipment usage",
    "nurse_to_patient_ratio": "Nurse-to-patient ratio",
    "doctor_available": "Doctors available",
    "year": "Year of the record",
    "month": "Month of the record",
    "day": "Day of the month",
    "hour": "Hour of the day",
    "day_of_week": "Day of the week",
}

# Order used to compare how serious two capacity statuses are.
STATUS_ORDER = {"Stable": 0, "Warning": 1, "High Risk": 2}


def get_hospital_label(hospital_id):
    """Return a simple display name such as Hospital 7 for a dataset hospital id."""
    return "Hospital " + str(int(hospital_id))


def get_feature_label(feature_name):
    """Return a readable label for a feature column, including one-hot columns."""
    if feature_name in FEATURE_LABELS:
        return FEATURE_LABELS[feature_name]
    if feature_name.startswith("hospital_id_text_"):
        return "Hospital " + feature_name.replace("hospital_id_text_", "")
    if feature_name.startswith("disaster_type_"):
        return "Disaster type: " + feature_name.replace("disaster_type_", "")
    if feature_name.startswith("triage_level_"):
        return "Triage level: " + feature_name.replace("triage_level_", "")
    if feature_name.startswith("injury_type_"):
        return "Injury type: " + feature_name.replace("injury_type_", "")
    return feature_name


# =============================================================================
# SECTION 4: LOAD AND VALIDATE THE DATASET
# This section reads the CSV file and checks that every required column exists.
# It does not clean values and does not train anything.
# =============================================================================

def load_dataset(dataset_path):
    """Read the CSV file from disk and return a pandas DataFrame."""
    if dataset_path == "":
        raise ValueError("DATASET_PATH is missing in the .env file.")
    if not os.path.exists(dataset_path):
        raise ValueError("The dataset file was not found. Check DATASET_PATH in the .env file.")

    data = pd.read_csv(dataset_path)

    # Remove accidental spaces around the column names.
    clean_names = []
    for column_name in data.columns:
        clean_names.append(str(column_name).strip())
    data.columns = clean_names

    return data


def validate_columns(data):
    """Return the list of required columns that are missing from the dataset."""
    missing_columns = []
    for column_name in REQUIRED_COLUMNS:
        if column_name not in data.columns:
            missing_columns.append(column_name)
    return missing_columns


# =============================================================================
# SECTION 5: CLEAN DATA AND CREATE TIME FEATURES
# This section removes duplicates and invalid rows, fixes impossible values and
# builds the time features. It does not split the data and does not encode text.
# =============================================================================

def clean_dataset(data):
    """Clean the raw dataset honestly and add the time feature columns."""
    clean = data.copy()

    # Drop only exact duplicate rows.
    clean = clean.drop_duplicates()

    # Parse timestamps and numeric schema values before deciding which target
    # rows are usable. This prevents invalid target text from reaching sklearn.
    clean["timestamp"] = pd.to_datetime(clean["timestamp"], errors="coerce")
    numeric_columns = NUMERIC_INPUT_COLUMNS + REGRESSION_TARGETS + ["hospital_id"]
    for column_name in numeric_columns:
        clean[column_name] = pd.to_numeric(clean[column_name], errors="coerce")
    clean[numeric_columns] = clean[numeric_columns].replace([np.inf, -np.inf], np.nan)

    # Capacity labels are a closed schema. Unexpected labels are unusable
    # targets rather than a fourth operational state.
    clean[CLASSIFICATION_TARGET] = clean[CLASSIFICATION_TARGET].astype("string").str.strip()
    clean.loc[~clean[CLASSIFICATION_TARGET].isin(STATUS_ORDER.keys()), CLASSIFICATION_TARGET] = pd.NA

    # Rows without a valid timestamp, identifier or target cannot be used for
    # training or dataset-record comparisons.
    clean = clean.dropna(subset=["timestamp", "hospital_id"] + OUTPUT_COLUMNS)

    # hospital_id is a positive whole-number identifier; fractional values are
    # rejected instead of silently being truncated into another hospital.
    valid_hospital_id = (clean["hospital_id"] >= 1.0) & (clean["hospital_id"] % 1.0 == 0.0)
    clean = clean[valid_hospital_id]
    clean["hospital_id"] = clean["hospital_id"].astype(int)
    clean["hospital_id_text"] = clean["hospital_id"].astype(str)

    # Missing category values are filled with a clear Unknown label.
    for column_name in ["disaster_type", "triage_level", "injury_type"]:
        clean[column_name] = clean[column_name].astype("string").fillna("Unknown").str.strip()
        clean[column_name] = clean[column_name].replace("", "Unknown").astype(str)

    clean[CLASSIFICATION_TARGET] = clean[CLASSIFICATION_TARGET].astype(str)

    # A tiny negative distance is a measurement error, so it is clipped to zero.
    clean["incident_distance_km"] = clean["incident_distance_km"].clip(lower=0.0)

    # Rate columns must stay inside the 0 to 1 range.
    for column_name in RATE_COLUMNS:
        clean[column_name] = clean[column_name].clip(lower=0.0, upper=1.0)

    # Counts, times and ratios can never be negative.
    non_negative_columns = [
        "ambulance_arrivals_per_hour",
        "patient_arrival_rate",
        "avg_treatment_time_min",
        "nurse_to_patient_ratio",
        "doctor_available",
        "predicted_patients_next_2h",
        "required_icu_beds",
        "required_ventilators",
        "required_staff",
    ]
    for column_name in non_negative_columns:
        clean[column_name] = clean[column_name].clip(lower=0.0)

    # Build the simple time features from the timestamp.
    clean["year"] = clean["timestamp"].dt.year
    clean["month"] = clean["timestamp"].dt.month
    clean["day"] = clean["timestamp"].dt.day
    clean["hour"] = clean["timestamp"].dt.hour
    clean["day_of_week"] = clean["timestamp"].dt.dayofweek

    clean = clean.sort_values("timestamp").reset_index(drop=True)
    return clean


def build_dataset_overview(clean):
    """Create the dataset statistics that the overview section displays."""
    status_counts = clean[CLASSIFICATION_TARGET].value_counts()

    overview = {}
    overview["row_count"] = int(len(clean))
    overview["hospital_count"] = int(clean["hospital_id"].nunique())
    overview["start_timestamp"] = clean["timestamp"].min().strftime("%Y-%m-%d %H:%M")
    overview["end_timestamp"] = clean["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    overview["latest_timestamp"] = clean["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    overview["stable_records"] = int(status_counts.get("Stable", 0))
    overview["warning_records"] = int(status_counts.get("Warning", 0))
    overview["high_risk_records"] = int(status_counts.get("High Risk", 0))
    overview["most_common_disaster_type"] = str(clean["disaster_type"].value_counts().index[0])
    return overview


def build_category_options(clean):
    """Collect dropdown options directly from the cleaned dataset."""
    hospital_list = []
    for hospital_id in sorted(clean["hospital_id"].unique().tolist()):
        hospital_list.append({"id": int(hospital_id), "label": get_hospital_label(hospital_id)})

    options = {}
    options["hospitals"] = hospital_list
    options["disaster_types"] = sorted(clean["disaster_type"].unique().tolist())
    options["triage_levels"] = sorted(clean["triage_level"].unique().tolist())
    options["injury_types"] = sorted(clean["injury_type"].unique().tolist())
    options["capacity_statuses"] = sorted(clean[CLASSIFICATION_TARGET].unique().tolist())
    return options


# =============================================================================
# SECTION 6: CREATE CHRONOLOGICAL TRAIN AND TEST DATA
# This section splits the data by time so the test set is always in the future.
# It also fills missing numeric values with the training median only.
# =============================================================================

def split_by_time(clean):
    """Split the data using the earliest 80 percent of the unique timestamps."""
    unique_timestamps = np.sort(clean["timestamp"].unique())
    total_timestamps = len(unique_timestamps)

    if total_timestamps < 5:
        raise ValueError("The dataset does not contain enough different timestamps for a time split.")

    # The cut position keeps the same timestamp on one side only.
    cut_position = int(total_timestamps * 0.8) - 1
    if cut_position < 0:
        cut_position = 0
    cut_timestamp = pd.Timestamp(unique_timestamps[cut_position])

    train = clean[clean["timestamp"] <= cut_timestamp].copy()
    test = clean[clean["timestamp"] > cut_timestamp].copy()

    if len(train) == 0 or len(test) == 0:
        raise ValueError("The chronological split produced an empty training or testing set.")

    return train, test


def fill_missing_numeric_values(train, test, clean):
    """Fill missing numeric feature values with the training median only."""
    training_medians = {}
    for column_name in NUMERIC_INPUT_COLUMNS:
        median_value = train[column_name].median()
        if pd.isna(median_value):
            median_value = 0.0
        training_medians[column_name] = float(median_value)

        train[column_name] = train[column_name].fillna(median_value)
        test[column_name] = test[column_name].fillna(median_value)
        clean[column_name] = clean[column_name].fillna(median_value)

    return training_medians


def build_training_ranges(train, training_medians):
    """Store the observed training minimum, maximum and median of every input."""
    ranges = {}
    for column_name in NUMERIC_INPUT_COLUMNS:
        ranges[column_name] = {
            "min": float(train[column_name].min()),
            "max": float(train[column_name].max()),
            "median": float(training_medians[column_name]),
        }
    return ranges


def build_split_info(train, test):
    """Describe the training and testing periods for the interface."""
    info = {}
    info["train_start"] = train["timestamp"].min().strftime("%Y-%m-%d %H:%M")
    info["train_end"] = train["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    info["test_start"] = test["timestamp"].min().strftime("%Y-%m-%d %H:%M")
    info["test_end"] = test["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    info["train_rows"] = int(len(train))
    info["test_rows"] = int(len(test))
    info["shared_timestamps"] = int(len(set(train["timestamp"]).intersection(set(test["timestamp"]))))
    return info


# =============================================================================
# SECTION 7: ENCODE CATEGORICAL FEATURES
# This section turns text columns into one-hot columns with pandas get_dummies.
# It never adds an output column to the feature matrix, so leakage cannot happen.
# =============================================================================

def build_raw_feature_frame(data):
    """Select only the current-condition columns that are allowed as model input."""
    wanted_columns = NUMERIC_INPUT_COLUMNS + TIME_FEATURE_COLUMNS + CATEGORICAL_FEATURE_COLUMNS
    return data[wanted_columns].copy()


def encode_training_features(train):
    """Create the training feature matrix and remember its exact column list."""
    raw_frame = build_raw_feature_frame(train)
    encoded = pd.get_dummies(raw_frame, columns=CATEGORICAL_FEATURE_COLUMNS)
    encoded = encoded.astype(float)
    return encoded


def encode_other_features(data):
    """Encode any other rows and align them to the saved training columns."""
    raw_frame = build_raw_feature_frame(data)
    encoded = pd.get_dummies(raw_frame, columns=CATEGORICAL_FEATURE_COLUMNS)
    # Missing dummy columns are filled with zero so the shape always matches.
    encoded = encoded.reindex(columns=FEATURE_COLUMNS, fill_value=0)
    encoded = encoded.astype(float)
    return encoded


def build_input_frame(records):
    """Turn a list of simple input dictionaries into a frame ready for encoding."""
    rows = []
    for record in records:
        row = {}
        for column_name in NUMERIC_INPUT_COLUMNS:
            row[column_name] = float(record[column_name])

        row["hospital_id_text"] = str(int(record["hospital_id"]))
        row["disaster_type"] = str(record["disaster_type"])
        row["triage_level"] = str(record["triage_level"])
        row["injury_type"] = str(record["injury_type"])

        stamp = pd.to_datetime(record["timestamp"])
        row["year"] = int(stamp.year)
        row["month"] = int(stamp.month)
        row["day"] = int(stamp.day)
        row["hour"] = int(stamp.hour)
        row["day_of_week"] = int(stamp.dayofweek)

        rows.append(row)

    return pd.DataFrame(rows)


# =============================================================================
# SECTION 8: TRAIN THE REGRESSION AND CLASSIFICATION MODELS
# This section trains one multi-output forest and one classifier a single time.
# It does not evaluate the models and does not save any model file.
# =============================================================================

def train_regression_model(x_train, y_train):
    """Train one random forest that predicts the five continuous outputs together."""
    model = RandomForestRegressor(
        n_estimators=120,
        max_depth=18,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    return model


def train_classification_model(x_train, y_train):
    """Train one random forest that predicts the capacity status label."""
    model = RandomForestClassifier(
        n_estimators=120,
        max_depth=18,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    return model


# =============================================================================
# SECTION 9: CALCULATE HELD-OUT TEST METRICS
# This section measures quality on the future test period only.
# It never reports training scores and never replaces a weak score.
# =============================================================================

def calculate_regression_metrics(model, x_test, y_test):
    """Calculate R squared and mean absolute error for every continuous target."""
    predictions = model.predict(x_test)

    metrics = []
    for index in range(len(REGRESSION_TARGETS)):
        target_name = REGRESSION_TARGETS[index]
        true_values = y_test[target_name].values
        predicted_values = predictions[:, index]

        metrics.append({
            "target": target_name,
            "label": TARGET_LABELS[target_name],
            "unit": TARGET_UNITS[target_name],
            "r2": float(r2_score(true_values, predicted_values)),
            "mae": float(mean_absolute_error(true_values, predicted_values)),
        })

    return metrics


def calculate_classification_metrics(model, x_test, y_test):
    """Calculate accuracy, macro F1, the confusion matrix and per-class recall."""
    predicted_labels = model.predict(x_test)
    class_labels = {str(label) for label in model.classes_}
    class_labels.update(str(label) for label in pd.Series(y_test).dropna().unique().tolist())
    class_labels = sorted(
        class_labels,
        key=lambda label: (STATUS_ORDER.get(label, len(STATUS_ORDER)), label),
    )

    matrix = confusion_matrix(y_test, predicted_labels, labels=class_labels)

    # Recall for one class is correct predictions divided by observed cases of that class.
    per_class_recall = {}
    for row_index in range(len(class_labels)):
        row_total = int(matrix[row_index].sum())
        if row_total > 0:
            per_class_recall[str(class_labels[row_index])] = float(matrix[row_index][row_index]) / float(row_total)
        else:
            per_class_recall[str(class_labels[row_index])] = None

    matrix_rows = []
    for row_index in range(len(class_labels)):
        matrix_rows.append([int(value) for value in matrix[row_index]])

    metrics = {}
    metrics["accuracy"] = float(accuracy_score(y_test, predicted_labels))
    metrics["macro_f1"] = float(f1_score(y_test, predicted_labels, average="macro", zero_division=0))
    metrics["labels"] = [str(label) for label in class_labels]
    metrics["confusion_matrix"] = matrix_rows
    metrics["per_class_recall"] = per_class_recall
    return metrics


def calculate_feature_importances(model, feature_columns):
    """Return the ten strongest global features of the regression model."""
    importance_values = model.feature_importances_

    pairs = []
    for index in range(len(feature_columns)):
        pairs.append({
            "feature": feature_columns[index],
            "label": get_feature_label(feature_columns[index]),
            "importance": float(importance_values[index]),
        })

    pairs.sort(key=get_importance_value, reverse=True)
    return pairs[:10]


def get_importance_value(item):
    """Small helper used to sort the feature importance list."""
    return item["importance"]


# =============================================================================
# SECTION 10: PREPARE ONE USER INPUT ROW
# This section turns validated user values into one clean prediction record.
# It does not call the models and does not build any strategy text.
# =============================================================================

def build_record_from_input(clean_input):
    """Create one simple record dictionary from the validated user input."""
    record = {}
    record["hospital_id"] = int(clean_input["hospital_id"])
    record["timestamp"] = clean_input["timestamp"]
    record["disaster_type"] = clean_input["disaster_type"]
    record["triage_level"] = clean_input["triage_level"]
    record["injury_type"] = clean_input["injury_type"]
    for column_name in NUMERIC_INPUT_COLUMNS:
        record[column_name] = float(clean_input[column_name])
    return record


def build_record_from_dataset_row(row):
    """Create the same kind of record from one row of the cleaned dataset."""
    record = {}
    record["hospital_id"] = int(row["hospital_id"])
    record["timestamp"] = row["timestamp"]
    record["disaster_type"] = str(row["disaster_type"])
    record["triage_level"] = str(row["triage_level"])
    record["injury_type"] = str(row["injury_type"])
    for column_name in NUMERIC_INPUT_COLUMNS:
        record[column_name] = float(row[column_name])
    return record


def build_display_record(record):
    """Create an interface friendly copy where rate columns are percentages."""
    display = {}
    display["hospital_id"] = int(record["hospital_id"])
    display["hospital_label"] = get_hospital_label(record["hospital_id"])
    display["timestamp"] = pd.to_datetime(record["timestamp"]).strftime("%Y-%m-%d %H:%M")
    display["timestamp_input"] = pd.to_datetime(record["timestamp"]).strftime("%Y-%m-%dT%H:%M")
    display["disaster_type"] = record["disaster_type"]
    display["triage_level"] = record["triage_level"]
    display["injury_type"] = record["injury_type"]
    display["incident_distance_km"] = round(float(record["incident_distance_km"]), 2)
    display["ambulance_arrivals_per_hour"] = round(float(record["ambulance_arrivals_per_hour"]), 2)
    display["patient_arrival_rate"] = round(float(record["patient_arrival_rate"]), 2)
    display["avg_treatment_time_min"] = round(float(record["avg_treatment_time_min"]), 1)
    display["nurse_to_patient_ratio"] = round(float(record["nurse_to_patient_ratio"]), 3)
    display["doctor_available"] = round(float(record["doctor_available"]), 1)
    display["mortality_risk_percent"] = round(float(record["mortality_risk_score"]) * 100.0, 1)
    display["bed_occupancy_percent"] = round(float(record["bed_occupancy_rate"]) * 100.0, 1)
    display["icu_occupancy_percent"] = round(float(record["icu_occupancy_rate"]) * 100.0, 1)
    display["equipment_usage_percent"] = round(float(record["equipment_usage_rate"]) * 100.0, 1)
    return display


# =============================================================================
# SECTION 11: MAKE PREDICTIONS AND UNCERTAINTY RANGES
# This section runs both trained models and builds the likely model ranges.
# It does not invent any confidence percentage of its own.
# =============================================================================

def predict_records(records):
    """Predict every output for a list of records and return simple dictionaries."""
    input_frame = build_input_frame(records)
    feature_frame = encode_other_features(input_frame)

    regression_values = REGRESSION_MODEL.predict(feature_frame)
    predicted_status = CLASSIFICATION_MODEL.predict(feature_frame)
    status_probabilities = CLASSIFICATION_MODEL.predict_proba(feature_frame)
    class_labels = list(CLASSIFICATION_MODEL.classes_)

    results = []
    for row_index in range(len(records)):
        result = {}

        # Negative operational values are not meaningful, so they are clipped.
        for target_index in range(len(REGRESSION_TARGETS)):
            target_name = REGRESSION_TARGETS[target_index]
            raw_value = float(regression_values[row_index][target_index])
            if raw_value < 0.0:
                raw_value = 0.0
            result[target_name] = raw_value

        # Overload risk always stays inside the 0 to 1 range.
        if result["overload_risk_score"] > 1.0:
            result["overload_risk_score"] = 1.0

        chosen_status = str(predicted_status[row_index])
        probability_row = status_probabilities[row_index]

        probabilities = {}
        for label_index in range(len(class_labels)):
            probabilities[str(class_labels[label_index])] = float(probability_row[label_index])

        result["capacity_status"] = chosen_status
        result["capacity_confidence"] = float(probabilities.get(chosen_status, 0.0))
        result["capacity_probabilities"] = probabilities
        results.append(result)

    return results, feature_frame


def calculate_prediction_ranges(feature_frame):
    """Use the individual trees of the forest to build a likely model range."""
    tree_predictions = []
    for single_tree in REGRESSION_MODEL.estimators_:
        tree_predictions.append(single_tree.predict(feature_frame.values))

    # Shape of the stack is (number of trees, number of rows, number of targets).
    stacked = np.array(tree_predictions)

    ranges = {}
    for target_index in range(len(REGRESSION_TARGETS)):
        target_name = REGRESSION_TARGETS[target_index]
        target_values = stacked[:, 0, target_index]

        low_value = float(np.percentile(target_values, 10))
        high_value = float(np.percentile(target_values, 90))

        if low_value < 0.0:
            low_value = 0.0
        if high_value < 0.0:
            high_value = 0.0

        ranges[target_name] = {"low": low_value, "high": high_value}

    return ranges


def build_prediction_cards(prediction, ranges):
    """Turn raw model numbers into rounded values that operations staff can use."""
    cards = {}

    # Patients are shown with a sensible rounded value.
    patients_raw = prediction["predicted_patients_next_2h"]
    cards["patients_next_2h"] = {
        "raw": patients_raw,
        "value": int(round(patients_raw)),
        "low": int(round(ranges["predicted_patients_next_2h"]["low"])),
        "high": int(round(ranges["predicted_patients_next_2h"]["high"])),
        "unit": "patients",
    }

    # Physical resources are rounded up because half a bed cannot be used.
    resource_map = {
        "icu_beds": ["required_icu_beds", "ICU beds"],
        "ventilators": ["required_ventilators", "ventilators"],
        "staff": ["required_staff", "staff units"],
    }
    for card_key in resource_map:
        target_name = resource_map[card_key][0]
        unit_text = resource_map[card_key][1]
        raw_value = prediction[target_name]
        cards[card_key] = {
            "raw": raw_value,
            "value": int(math.ceil(raw_value)),
            "low": int(math.ceil(ranges[target_name]["low"])),
            "high": int(math.ceil(ranges[target_name]["high"])),
            "unit": unit_text,
        }

    # Overload risk is displayed as a percentage between 0 and 100.
    risk_raw = prediction["overload_risk_score"]
    cards["overload_risk"] = {
        "raw": risk_raw,
        "value": round(risk_raw * 100.0, 1),
        "low": round(min(max(ranges["overload_risk_score"]["low"], 0.0), 1.0) * 100.0, 1),
        "high": round(min(max(ranges["overload_risk_score"]["high"], 0.0), 1.0) * 100.0, 1),
        "unit": "%",
    }

    return cards


def calculate_resilience_index(prediction, record):
    """Build the transparent operational resilience index between 0 and 100."""
    overload_part = 0.35 * float(prediction["overload_risk_score"])
    bed_part = 0.25 * float(record["bed_occupancy_rate"])
    icu_part = 0.25 * float(record["icu_occupancy_rate"])
    equipment_part = 0.15 * float(record["equipment_usage_rate"])

    pressure = overload_part + bed_part + icu_part + equipment_part
    index_value = 100.0 * (1.0 - pressure)

    if index_value < 0.0:
        index_value = 0.0
    if index_value > 100.0:
        index_value = 100.0

    if index_value >= 70.0:
        status_text = "Strong operational position"
    elif index_value >= 45.0:
        status_text = "Pressured but manageable"
    else:
        status_text = "Severe operational pressure"

    result = {}
    result["index"] = round(index_value, 1)
    result["status"] = status_text
    result["formula"] = ("pressure = 0.35 x predicted overload risk + 0.25 x bed occupancy "
                         "+ 0.25 x ICU occupancy + 0.15 x equipment usage, "
                         "then resilience index = 100 x (1 - pressure)")
    result["components"] = {
        "overload_component": round(overload_part * 100.0, 1),
        "bed_component": round(bed_part * 100.0, 1),
        "icu_component": round(icu_part * 100.0, 1),
        "equipment_component": round(equipment_part * 100.0, 1),
        "total_pressure_percent": round(pressure * 100.0, 1),
    }
    return result


def build_pressure_factors(record):
    """List up to five input values that are associated with higher pressure."""
    candidates = []

    # Every factor compares one input with the training-set median.
    above_median_checks = [
        ["icu_occupancy_rate", "ICU occupancy is above the training-set median", True],
        ["bed_occupancy_rate", "Bed occupancy is above the training-set median", True],
        ["equipment_usage_rate", "Equipment usage is above the training-set median", True],
        ["ambulance_arrivals_per_hour", "Ambulance arrivals are above the training-set median", False],
        ["patient_arrival_rate", "Patient arrival rate is above the training-set median", False],
        ["mortality_risk_score", "Mortality risk is above the training-set median", True],
        ["avg_treatment_time_min", "Average treatment time is above the training-set median", False],
    ]

    for check in above_median_checks:
        column_name = check[0]
        title_text = check[1]
        is_percent = check[2]

        median_value = TRAINING_RANGES[column_name]["median"]
        current_value = float(record[column_name])

        if median_value <= 0.0:
            continue
        strength = (current_value - median_value) / median_value
        if strength <= 0.05:
            continue

        if is_percent:
            detail_text = ("Current value " + str(round(current_value * 100.0, 1)) +
                           "% compared with a training-set median of " +
                           str(round(median_value * 100.0, 1)) + "%.")
        else:
            detail_text = ("Current value " + str(round(current_value, 2)) +
                           " compared with a training-set median of " +
                           str(round(median_value, 2)) + ".")

        candidates.append({"title": title_text, "detail": detail_text, "strength": strength})

    # A short distance means the hospital is close to the incident.
    distance_median = TRAINING_RANGES["incident_distance_km"]["median"]
    distance_value = float(record["incident_distance_km"])
    if distance_median > 0.0 and distance_value < distance_median:
        strength = (distance_median - distance_value) / distance_median
        if strength > 0.05:
            candidates.append({
                "title": "The incident is closer to this hospital than usual",
                "detail": ("Distance " + str(round(distance_value, 1)) +
                           " km compared with a training-set median of " +
                           str(round(distance_median, 1)) + " km."),
                "strength": strength,
            })

    # A low nurse ratio means fewer nurses for each patient.
    nurse_median = TRAINING_RANGES["nurse_to_patient_ratio"]["median"]
    nurse_value = float(record["nurse_to_patient_ratio"])
    if nurse_median > 0.0 and nurse_value < nurse_median:
        strength = (nurse_median - nurse_value) / nurse_median
        if strength > 0.05:
            candidates.append({
                "title": "Nurse-to-patient ratio is below the training-set median",
                "detail": ("Current ratio " + str(round(nurse_value, 3)) +
                           " compared with a training-set median of " +
                           str(round(nurse_median, 3)) + "."),
                "strength": strength,
            })

    # Fewer available doctors than usual also increases operational pressure.
    doctor_median = TRAINING_RANGES["doctor_available"]["median"]
    doctor_value = float(record["doctor_available"])
    if doctor_median > 0.0 and doctor_value < doctor_median:
        strength = (doctor_median - doctor_value) / doctor_median
        if strength > 0.05:
            candidates.append({
                "title": "Fewer doctors available than the training-set median",
                "detail": ("Currently " + str(round(doctor_value, 1)) +
                           " compared with a training-set median of " +
                           str(round(doctor_median, 1)) + "."),
                "strength": strength,
            })

    candidates.sort(key=get_strength_value, reverse=True)

    factors = []
    for item in candidates[:5]:
        factors.append({"title": item["title"], "detail": item["detail"]})

    if len(factors) == 0:
        factors.append({
            "title": "No input value is clearly above the training-set median",
            "detail": "The entered condition looks close to or below the training-set medians for this dataset.",
        })

    return factors


def get_strength_value(item):
    """Small helper used to sort the pressure factor list."""
    return item["strength"]


# =============================================================================
# SECTION 12: FIND SIMILAR DATASET RECORDS
# This section searches CSV rows that look like the current situation.
# It never creates simulated scenarios and only reports observed outcomes.
# =============================================================================

def find_similar_cases(record):
    """Find the nearest dataset rows and summarise their recorded outcomes."""
    same_type = CLEAN_DATA["disaster_type"] == record["disaster_type"]
    same_triage = CLEAN_DATA["triage_level"] == record["triage_level"]

    # Step one: the same disaster type and the same triage level.
    subset = CLEAN_DATA[same_type & same_triage]
    filter_used = "Same disaster type and same triage level"

    # Step two: only the same disaster type when the first filter is too small.
    if len(subset) < 20:
        subset = CLEAN_DATA[same_type]
        filter_used = "Same disaster type"

    # Step three: the full dataset when even that is too small.
    if len(subset) < 20:
        subset = CLEAN_DATA
        filter_used = "Complete dataset"

    # Differences are normalised with the dataset standard deviation of each field.
    total_distance = np.zeros(len(subset))
    for column_name in SIMILARITY_COLUMNS:
        spread = float(CLEAN_DATA[column_name].std())
        if spread == 0.0 or pd.isna(spread):
            spread = 1.0
        difference = (subset[column_name].values - float(record[column_name])) / spread
        total_distance = total_distance + (difference * difference)

    subset = subset.copy()
    subset["similarity_distance"] = total_distance

    # A distance of exactly zero means the identical row, which is not a separate case.
    subset = subset[subset["similarity_distance"] > 0.0]

    if len(subset) == 0:
        return {
            "count": 0,
            "filter_used": filter_used,
            "message": "No comparable dataset record was found for this combination.",
        }

    nearest = subset.nsmallest(30, "similarity_distance")

    high_risk_rows = nearest[nearest[CLASSIFICATION_TARGET] == "High Risk"]
    high_risk_percent = 100.0 * float(len(high_risk_rows)) / float(len(nearest))

    summary = {}
    summary["count"] = int(len(nearest))
    summary["filter_used"] = filter_used
    summary["high_risk_percent"] = round(high_risk_percent, 1)
    summary["avg_patients_next_2h"] = round(float(nearest["predicted_patients_next_2h"].mean()), 1)
    summary["avg_required_icu_beds"] = round(float(nearest["required_icu_beds"].mean()), 1)
    summary["avg_required_ventilators"] = round(float(nearest["required_ventilators"].mean()), 1)
    summary["avg_required_staff"] = round(float(nearest["required_staff"].mean()), 1)
    summary["avg_overload_risk_percent"] = round(float(nearest["overload_risk_score"].mean()) * 100.0, 1)
    summary["min_overload_risk_percent"] = round(float(nearest["overload_risk_score"].min()) * 100.0, 1)
    summary["max_overload_risk_percent"] = round(float(nearest["overload_risk_score"].max()) * 100.0, 1)
    summary["most_common_capacity_status"] = str(nearest[CLASSIFICATION_TARGET].value_counts().index[0])
    summary["message"] = ""
    return summary


# =============================================================================
# SECTION 13: CREATE RECOVERY STRATEGIES
# This section builds rule-based recovery actions from the current prediction result.
# It gives operational suggestions only and never gives clinical treatment advice.
# =============================================================================

def create_recovery_strategies(cards, capacity_status, resilience, record, coordination_candidates):
    """Create the four recovery strategy groups from the current prediction."""
    immediate_priorities = []
    next_two_hours = []
    monitoring_priorities = []
    coordination_options = []

    icu_needed = cards["icu_beds"]["value"]
    ventilators_needed = cards["ventilators"]["value"]
    staff_needed = cards["staff"]["value"]
    patients_expected = cards["patients_next_2h"]["value"]
    risk_percent = cards["overload_risk"]["value"]

    # Group A and B change with the capacity status returned by the classifier.
    if capacity_status == "High Risk":
        immediate_priorities.append("Activating the hospital surge-response procedure should be considered now.")
        immediate_priorities.append("Directing the available emergency reserve towards ICU and ventilator demand is a priority based on the model output.")
        immediate_priorities.append("Opening prepared overflow treatment areas may help absorb the expected arrivals.")
        immediate_priorities.append("Informing the emergency-management coordinator about the predicted overload risk of " + str(risk_percent) + "% should be considered.")
        next_two_hours.append("Preparing at least " + str(icu_needed) + " ICU bed places for the next two hours is suggested by the model.")
        next_two_hours.append("Checking that " + str(ventilators_needed) + " ventilators can be made ready may help.")
        next_two_hours.append("Calling in additional staff towards the estimated need of " + str(staff_needed) + " staff units should be considered.")
        next_two_hours.append("Planning triage space for about " + str(patients_expected) + " expected patients is advisable.")
    elif capacity_status == "Warning":
        immediate_priorities.append("Staging additional staff and equipment close to the emergency department should be considered.")
        immediate_priorities.append("Preparing ICU escalation capacity before demand rises may help.")
        immediate_priorities.append("Keeping part of the emergency reserve unallocated allows a response if the situation deteriorates.")
        next_two_hours.append("Reserving about " + str(icu_needed) + " ICU bed places for the next two hours is suggested by the model.")
        next_two_hours.append("Confirming that " + str(ventilators_needed) + " ventilators are serviceable and reachable may help.")
        next_two_hours.append("Reviewing whether " + str(staff_needed) + " staff units can be covered by the current roster is advisable.")
        next_two_hours.append("Preparing intake flow for about " + str(patients_expected) + " expected patients should be considered.")
    else:
        immediate_priorities.append("Maintaining the current readiness level is reasonable based on the model output.")
        immediate_priorities.append("Protecting the emergency reserve for hospitals under higher pressure should be considered.")
        immediate_priorities.append("Continuing normal admission and discharge planning may help keep capacity free.")
        next_two_hours.append("Keeping about " + str(icu_needed) + " ICU bed places reachable for the next two hours is suggested by the model.")
        next_two_hours.append("Verifying that " + str(ventilators_needed) + " ventilators remain available is advisable.")
        next_two_hours.append("Confirming that the roster covers about " + str(staff_needed) + " staff units may help.")
        next_two_hours.append("Planning for about " + str(patients_expected) + " expected patients is enough at the current status.")

    # Group C is built from the current values that are highest right now.
    if float(record["icu_occupancy_rate"]) >= 0.85:
        monitoring_priorities.append("ICU occupancy is at " + str(round(float(record["icu_occupancy_rate"]) * 100.0, 1)) + "%, so it should be reviewed frequently.")
    else:
        monitoring_priorities.append("ICU occupancy is at " + str(round(float(record["icu_occupancy_rate"]) * 100.0, 1)) + "% and should be checked regularly.")

    monitoring_priorities.append("Bed occupancy is at " + str(round(float(record["bed_occupancy_rate"]) * 100.0, 1)) + "% and is a useful early warning indicator.")
    monitoring_priorities.append("Equipment usage is at " + str(round(float(record["equipment_usage_rate"]) * 100.0, 1)) + "% and limits how fast new patients can be treated.")
    monitoring_priorities.append("Ambulance arrivals are " + str(round(float(record["ambulance_arrivals_per_hour"]), 1)) + " per hour, so a sudden rise should trigger a new analysis.")
    monitoring_priorities.append("The derived resilience index is " + str(resilience["index"]) + " out of 100, described as " + resilience["status"].lower() + ".")

    # Group D lists possible coordination partners found from the model output.
    if len(coordination_candidates) == 0:
        coordination_options.append("No hospital in the dataset currently shows clearly lower pressure than this one, so internal capacity measures are the main option.")
    else:
        for candidate in coordination_candidates:
            coordination_options.append(
                candidate["hospital_label"] + " is a possible lower-pressure coordination candidate with a predicted overload risk of " +
                str(candidate["overload_risk_percent"]) + "% and a predicted status of " + candidate["capacity_status"] + "."
            )

    coordination_options.append("Actual transfer feasibility requires verified capacity, transport, clinical and local operational information that is not included in this dataset.")

    strategies = {}
    strategies["immediate_priorities"] = immediate_priorities
    strategies["next_two_hours"] = next_two_hours
    strategies["monitoring_priorities"] = monitoring_priorities
    strategies["coordination_options"] = coordination_options
    return strategies


def create_decision_recommendations(cards, capacity_status, resilience, similar_cases, record):
    """Create short decision-support recommendations from the result values."""
    recommendations = []

    risk_percent = cards["overload_risk"]["value"]

    recommendations.append({
        "title": "Reserve prioritisation",
        "detail": ("The model output places this hospital at a predicted overload risk of " + str(risk_percent) +
                   "% with a capacity status of " + capacity_status +
                   ". Entering the currently available emergency reserve in the allocation section will rank it against the other hospitals."),
    })

    recommendations.append({
        "title": "Escalation trigger",
        "detail": ("A useful escalation trigger is the likely model range for ICU demand, which is " +
                   str(cards["icu_beds"]["low"]) + " to " + str(cards["icu_beds"]["high"]) +
                   " beds. Planning for the upper end should be considered when the situation is still developing."),
    })

    recommendations.append({
        "title": "Staffing decision",
        "detail": ("The estimated staff requirement is " + str(cards["staff"]["value"]) + " staff units with a likely model range of " +
                   str(cards["staff"]["low"]) + " to " + str(cards["staff"]["high"]) +
                   ". This estimate is not a direct comparison with the " + str(round(float(record["doctor_available"]), 1)) +
                   " doctors currently available, because the dataset does not confirm that both values use the same unit."),
    })

    if similar_cases.get("count", 0) > 0:
        recommendations.append({
            "title": "Comparison with similar dataset records",
            "detail": ("In " + str(similar_cases["count"]) + " similar dataset records, " + str(similar_cases["high_risk_percent"]) +
                       "% ended in a High Risk status and the average observed overload risk was " +
                       str(similar_cases["avg_overload_risk_percent"]) + "%. These are recorded dataset outcomes, not a forecast."),
        })
    else:
        recommendations.append({
            "title": "Comparison with similar dataset records",
            "detail": "No sufficiently similar dataset record was found, so the prediction should be treated with extra caution.",
        })

    recommendations.append({
        "title": "Operational resilience review",
        "detail": ("The derived resilience index is " + str(resilience["index"]) + " out of 100 (" + resilience["status"] +
                   "). It is a transparent summary created for this project and is not a medically validated score."),
    })

    recommendations.append({
        "title": "Validation requirement",
        "detail": ("Every recommendation on this page is decision support based on configured dataset records and a two-hour "
                   "prediction target. Qualified hospital and emergency-management staff must confirm the current bed, ventilator "
                   "and staffing situation before acting."),
    })

    return recommendations


# =============================================================================
# SECTION 14: CALCULATE MULTI-OBJECTIVE PRIORITY SCORES
# This section scores every hospital with four normalised objectives.
# It does not move any resource, that happens in the allocation section.
# =============================================================================

def normalise_weights(weights):
    """Turn the four entered objective weights into values that add up to one."""
    keys = ["patient_safety", "overload_relief", "patient_demand", "incident_proximity"]

    total = 0.0
    for key in keys:
        value = float(weights[key])
        if value < 0.0:
            value = 0.0
        total = total + value

    normalised = {}
    if total <= 0.0:
        # When every weight is zero the four objectives share the score equally.
        for key in keys:
            normalised[key] = 0.25
        return normalised

    for key in keys:
        value = float(weights[key])
        if value < 0.0:
            value = 0.0
        normalised[key] = value / total

    return normalised


def min_max_normalise(values):
    """Scale a list of numbers to the 0 to 1 range for the current hospital group."""
    if len(values) == 0:
        return []

    lowest = min(values)
    highest = max(values)

    normalised = []
    for value in values:
        # When every value is the same the normalised component is zero.
        if highest == lowest:
            normalised.append(0.0)
        else:
            normalised.append((value - lowest) / (highest - lowest))

    return normalised


def build_hospital_scenarios(selected_hospital_id, selected_record):
    """Collect the latest dataset record for every hospital and apply the user scenario."""
    records = []
    for row_index in range(len(LATEST_RECORDS)):
        row = LATEST_RECORDS.iloc[row_index]
        record = build_record_from_dataset_row(row)
        record["record_source"] = "Latest dataset record"

        # The selected hospital may use the values currently entered in the form.
        if selected_record is not None and int(record["hospital_id"]) == int(selected_hospital_id):
            record = dict(selected_record)
            record["record_source"] = "Current form scenario"

        records.append(record)

    return records


def calculate_priority_scores(records, predictions, normalised_weights):
    """Calculate the multi-objective operational priority score of every hospital."""
    mortality_values = []
    icu_requirement_values = []
    ventilator_requirement_values = []
    patient_values = []
    distance_values = []

    for index in range(len(records)):
        mortality_values.append(float(records[index]["mortality_risk_score"]))
        distance_values.append(float(records[index]["incident_distance_km"]))
        icu_requirement_values.append(float(predictions[index]["required_icu_beds"]))
        ventilator_requirement_values.append(float(predictions[index]["required_ventilators"]))
        patient_values.append(float(predictions[index]["predicted_patients_next_2h"]))

    normalised_mortality = min_max_normalise(mortality_values)
    normalised_icu_requirement = min_max_normalise(icu_requirement_values)
    normalised_ventilator_requirement = min_max_normalise(ventilator_requirement_values)
    normalised_patients = min_max_normalise(patient_values)
    normalised_distance = min_max_normalise(distance_values)

    scored_rows = []
    for index in range(len(records)):
        record = records[index]
        prediction = predictions[index]

        # Objective 1: patient safety pressure.
        patient_safety_component = (normalised_mortality[index] +
                                    normalised_icu_requirement[index] +
                                    normalised_ventilator_requirement[index]) / 3.0

        # Objective 2: relief of current operational overload.
        overload_relief_component = (float(prediction["overload_risk_score"]) +
                                     float(record["bed_occupancy_rate"]) +
                                     float(record["icu_occupancy_rate"]) +
                                     float(record["equipment_usage_rate"])) / 4.0

        # Objective 3: expected patient demand.
        patient_demand_component = normalised_patients[index]

        # Objective 4: closeness to the incident.
        incident_proximity_component = 1.0 - normalised_distance[index]

        weighted_total = (normalised_weights["patient_safety"] * patient_safety_component +
                          normalised_weights["overload_relief"] * overload_relief_component +
                          normalised_weights["patient_demand"] * patient_demand_component +
                          normalised_weights["incident_proximity"] * incident_proximity_component)

        priority_score = weighted_total * 100.0
        if priority_score < 0.0:
            priority_score = 0.0
        if priority_score > 100.0:
            priority_score = 100.0

        scored_rows.append({
            "hospital_id": int(record["hospital_id"]),
            "hospital_label": get_hospital_label(record["hospital_id"]),
            "record_source": record.get("record_source", "Latest dataset record"),
            "record_timestamp": pd.to_datetime(record["timestamp"]).strftime("%Y-%m-%d %H:%M"),
            "priority_score": round(priority_score, 2),
            "capacity_status": prediction["capacity_status"],
            "capacity_confidence_percent": round(float(prediction["capacity_confidence"]) * 100.0, 1),
            "overload_risk_percent": round(float(prediction["overload_risk_score"]) * 100.0, 1),
            "predicted_patients": int(round(float(prediction["predicted_patients_next_2h"]))),
            "predicted_icu_beds": int(math.ceil(float(prediction["required_icu_beds"]))),
            "predicted_ventilators": int(math.ceil(float(prediction["required_ventilators"]))),
            "predicted_staff": int(math.ceil(float(prediction["required_staff"]))),
            "bed_occupancy_percent": round(float(record["bed_occupancy_rate"]) * 100.0, 1),
            "icu_occupancy_percent": round(float(record["icu_occupancy_rate"]) * 100.0, 1),
            "equipment_usage_percent": round(float(record["equipment_usage_rate"]) * 100.0, 1),
            "incident_distance_km": round(float(record["incident_distance_km"]), 1),
            "components": {
                "patient_safety": round(patient_safety_component, 3),
                "overload_relief": round(overload_relief_component, 3),
                "patient_demand": round(patient_demand_component, 3),
                "incident_proximity": round(incident_proximity_component, 3),
            },
        })

    return scored_rows


def find_coordination_candidates(scored_rows, selected_hospital_id):
    """Find up to three hospitals that currently look less pressured than the selected one."""
    selected_row = None
    for row in scored_rows:
        if int(row["hospital_id"]) == int(selected_hospital_id):
            selected_row = row

    if selected_row is None:
        return []

    selected_status_rank = STATUS_ORDER.get(selected_row["capacity_status"], 1)

    candidates = []
    for row in scored_rows:
        if int(row["hospital_id"]) == int(selected_hospital_id):
            continue

        candidate_status_rank = STATUS_ORDER.get(row["capacity_status"], 1)

        # A candidate must be lower on every pressure measure that the dataset provides.
        if row["overload_risk_percent"] >= selected_row["overload_risk_percent"]:
            continue
        if row["icu_occupancy_percent"] >= selected_row["icu_occupancy_percent"]:
            continue
        if row["bed_occupancy_percent"] >= selected_row["bed_occupancy_percent"]:
            continue
        if candidate_status_rank > selected_status_rank:
            continue

        candidates.append({
            "hospital_id": row["hospital_id"],
            "hospital_label": row["hospital_label"],
            "capacity_status": row["capacity_status"],
            "overload_risk_percent": row["overload_risk_percent"],
            "icu_occupancy_percent": row["icu_occupancy_percent"],
            "bed_occupancy_percent": row["bed_occupancy_percent"],
            "note": "Possible lower-pressure coordination candidate",
        })

    candidates.sort(key=get_overload_value)
    return candidates[:3]


def get_overload_value(item):
    """Small helper used to sort coordination candidates by predicted overload risk."""
    return item["overload_risk_percent"]


# =============================================================================
# SECTION 15: ALLOCATE LIMITED EMERGENCY RESOURCES
# This section shares the reserve entered by the user between the hospitals.
# It never invents resources and never allocates more than the entered reserve.
# =============================================================================

def allocate_one_resource(scored_rows, need_key, available_units):
    """Share one limited reserve between the hospitals using their weighted need."""
    allocation = {}
    for row in scored_rows:
        allocation[row["hospital_id"]] = 0

    if available_units <= 0:
        return allocation, available_units

    # Step one: each hospital gets a weighted need based on its priority score.
    weighted_needs = {}
    integer_needs = {}
    total_weighted_need = 0.0

    for row in scored_rows:
        predicted_need = float(row[need_key])
        if predicted_need < 0.0:
            predicted_need = 0.0
        integer_need = int(math.ceil(predicted_need))
        weighted_need = integer_need * (1.0 + float(row["priority_score"]) / 100.0)

        integer_needs[row["hospital_id"]] = integer_need
        weighted_needs[row["hospital_id"]] = weighted_need
        total_weighted_need = total_weighted_need + weighted_need

    if total_weighted_need <= 0.0:
        return allocation, available_units

    # Step two: give every hospital the whole part of its proportional share.
    remainders = {}
    used_units = 0
    for row in scored_rows:
        hospital_id = row["hospital_id"]
        share = available_units * weighted_needs[hospital_id] / total_weighted_need
        base_units = int(math.floor(share))

        # A hospital never receives more than its estimated need.
        if base_units > integer_needs[hospital_id]:
            base_units = integer_needs[hospital_id]

        allocation[hospital_id] = base_units
        remainders[hospital_id] = share - math.floor(share)
        used_units = used_units + base_units

    remaining_units = available_units - used_units

    # Step three: give the leftover units one at a time, largest remainder first.
    sortable_rows = []
    for row in scored_rows:
        sortable_rows.append({
            "hospital_id": row["hospital_id"],
            "remainder": remainders[row["hospital_id"]],
            "priority_score": float(row["priority_score"]),
        })
    sortable_rows.sort(key=get_remainder_and_priority, reverse=True)

    keep_going = True
    while remaining_units > 0 and keep_going:
        keep_going = False
        for item in sortable_rows:
            if remaining_units <= 0:
                break
            hospital_id = item["hospital_id"]
            if allocation[hospital_id] < integer_needs[hospital_id]:
                allocation[hospital_id] = allocation[hospital_id] + 1
                remaining_units = remaining_units - 1
                keep_going = True

    return allocation, remaining_units


def get_remainder_and_priority(item):
    """Small helper that sorts by largest remainder first and then by priority."""
    return (item["remainder"], item["priority_score"])


def build_allocation_plan(scored_rows, reserve):
    """Run the allocation for ICU beds, ventilators and staff and check the totals."""
    icu_allocation, icu_left = allocate_one_resource(scored_rows, "predicted_icu_beds", reserve["icu_beds"])
    ventilator_allocation, ventilator_left = allocate_one_resource(scored_rows, "predicted_ventilators", reserve["ventilators"])
    staff_allocation, staff_left = allocate_one_resource(scored_rows, "predicted_staff", reserve["staff"])

    # Sort the hospitals by priority score so the report shows a clear ranking.
    ranked_rows = sorted(scored_rows, key=get_priority_value, reverse=True)

    total_icu = 0
    total_ventilators = 0
    total_staff = 0

    result_rows = []
    for position in range(len(ranked_rows)):
        row = dict(ranked_rows[position])
        hospital_id = row["hospital_id"]

        row["rank"] = position + 1
        row["icu_allocated"] = int(icu_allocation[hospital_id])
        row["ventilators_allocated"] = int(ventilator_allocation[hospital_id])
        row["staff_allocated"] = int(staff_allocation[hospital_id])

        total_icu = total_icu + row["icu_allocated"]
        total_ventilators = total_ventilators + row["ventilators_allocated"]
        total_staff = total_staff + row["staff_allocated"]

        result_rows.append(row)

    # Safety check: the plan can never hand out more than the entered reserve.
    if total_icu > reserve["icu_beds"] or total_ventilators > reserve["ventilators"] or total_staff > reserve["staff"]:
        raise ValueError("The allocation produced more units than the entered reserve.")

    plan = {}
    plan["rows"] = result_rows
    plan["total_allocated"] = {
        "icu_beds": int(total_icu),
        "ventilators": int(total_ventilators),
        "staff": int(total_staff),
    }
    plan["remaining_reserve"] = {
        "icu_beds": int(reserve["icu_beds"] - total_icu),
        "ventilators": int(reserve["ventilators"] - total_ventilators),
        "staff": int(reserve["staff"] - total_staff),
    }
    return plan


def get_priority_value(item):
    """Small helper used to rank hospitals by their priority score."""
    return item["priority_score"]


# =============================================================================
# SECTION 16: CREATE DATASET TIME-SERIES ANALYSIS
# This section reports weekly dataset values and simple trend directions.
# It does not create any long-term forecast, because the target covers two hours.
# =============================================================================

def calculate_trend(values):
    """Fit a simple straight line to the weekly values and classify the direction."""
    if len(values) < 3:
        return {"direction": "Not enough weekly points", "slope_per_week": None}

    week_index = np.arange(len(values)).reshape(-1, 1)
    target_values = np.array(values)

    trend_model = LinearRegression()
    trend_model.fit(week_index, target_values)
    slope = float(trend_model.coef_[0])

    if slope > TREND_SLOPE_THRESHOLD:
        direction = "Worsening"
    elif slope < -TREND_SLOPE_THRESHOLD:
        direction = "Improving"
    else:
        direction = "Stable"

    return {"direction": direction, "slope_per_week": round(slope, 5)}


def build_history_analysis(hospital_id):
    """Build the weekly dataset trend summary for one hospital."""
    hospital_rows = CLEAN_DATA[CLEAN_DATA["hospital_id"] == int(hospital_id)].copy()

    if len(hospital_rows) == 0:
        return None

    hospital_rows = hospital_rows.sort_values("timestamp")

    # Records are grouped into weekly periods using the start day of each week.
    hospital_rows["week_start"] = hospital_rows["timestamp"].dt.to_period("W").dt.start_time

    average_columns = [
        "overload_risk_score",
        "bed_occupancy_rate",
        "icu_occupancy_rate",
        "equipment_usage_rate",
        "predicted_patients_next_2h",
        "required_icu_beds",
        "required_ventilators",
        "required_staff",
    ]

    weekly = hospital_rows.groupby("week_start")[average_columns].mean().reset_index()
    weekly = weekly.sort_values("week_start")

    # Only the latest twelve weekly points are returned.
    weekly = weekly.tail(12)

    labels = []
    for week_value in weekly["week_start"]:
        labels.append(pd.Timestamp(week_value).strftime("%Y-%m-%d"))

    overload_percent = []
    bed_percent = []
    icu_percent = []
    equipment_percent = []
    patients_series = []
    icu_beds_series = []
    ventilators_series = []
    staff_series = []

    for row_index in range(len(weekly)):
        row = weekly.iloc[row_index]
        overload_percent.append(round(float(row["overload_risk_score"]) * 100.0, 1))
        bed_percent.append(round(float(row["bed_occupancy_rate"]) * 100.0, 1))
        icu_percent.append(round(float(row["icu_occupancy_rate"]) * 100.0, 1))
        equipment_percent.append(round(float(row["equipment_usage_rate"]) * 100.0, 1))
        patients_series.append(round(float(row["predicted_patients_next_2h"]), 1))
        icu_beds_series.append(round(float(row["required_icu_beds"]), 1))
        ventilators_series.append(round(float(row["required_ventilators"]), 1))
        staff_series.append(round(float(row["required_staff"]), 1))

    # Trends are calculated on the original 0 to 1 rates, not on the percentages.
    trends = {}
    trends["overload_risk"] = calculate_trend(weekly["overload_risk_score"].tolist())
    trends["bed_occupancy"] = calculate_trend(weekly["bed_occupancy_rate"].tolist())
    trends["icu_occupancy"] = calculate_trend(weekly["icu_occupancy_rate"].tolist())

    high_risk_rows = hospital_rows[hospital_rows[CLASSIFICATION_TARGET] == "High Risk"]

    summary = {}
    summary["record_count"] = int(len(hospital_rows))
    summary["first_record"] = hospital_rows["timestamp"].min().strftime("%Y-%m-%d %H:%M")
    summary["last_record"] = hospital_rows["timestamp"].max().strftime("%Y-%m-%d %H:%M")
    summary["min_overload_risk_percent"] = round(float(hospital_rows["overload_risk_score"].min()) * 100.0, 1)
    summary["avg_overload_risk_percent"] = round(float(hospital_rows["overload_risk_score"].mean()) * 100.0, 1)
    summary["max_overload_risk_percent"] = round(float(hospital_rows["overload_risk_score"].max()) * 100.0, 1)
    summary["high_risk_percent"] = round(100.0 * float(len(high_risk_rows)) / float(len(hospital_rows)), 1)

    analysis = {}
    analysis["hospital_id"] = int(hospital_id)
    analysis["hospital_label"] = get_hospital_label(hospital_id)
    analysis["weekly_labels"] = labels
    analysis["weekly_values"] = {
        "overload_risk_percent": overload_percent,
        "bed_occupancy_percent": bed_percent,
        "icu_occupancy_percent": icu_percent,
        "equipment_usage_percent": equipment_percent,
        "predicted_patients_next_2h": patients_series,
        "required_icu_beds": icu_beds_series,
        "required_ventilators": ventilators_series,
        "required_staff": staff_series,
    }
    analysis["trends"] = trends
    analysis["trend_threshold"] = TREND_SLOPE_THRESHOLD
    analysis["summary"] = summary
    analysis["note"] = ("The dataset contains a validated two-hour prediction target. The sustainability panel therefore "
                        "reports weekly dataset trends rather than inventing unsupported long-term forecasts.")
    return analysis


# =============================================================================
# SECTION 17: VALIDATE API INPUTS
# This section checks every value that arrives from the browser.
# It rejects impossible values and warns about values outside the training range.
# =============================================================================

def ensure_json_object(payload, object_name="request body"):
    """Return a bounded validation message unless payload is a JSON object."""
    if not isinstance(payload, dict):
        return "The " + object_name + " must be a JSON object."
    return ""


def read_number(payload, field_name, maximum=None):
    """Read one number and reject booleans, containers, infinity and extremes."""
    object_error = ensure_json_object(payload)
    if object_error != "":
        return None, object_error
    if field_name not in payload:
        return None, "The field " + field_name + " is missing."

    raw_value = payload[field_name]
    if raw_value is None:
        return None, "The field " + field_name + " is empty."
    if isinstance(raw_value, bool):
        return None, "The field " + field_name + " must be a number, not a boolean."
    if isinstance(raw_value, str) and raw_value.strip() == "":
        return None, "The field " + field_name + " is empty."
    if isinstance(raw_value, str) and len(raw_value) > 100:
        return None, "The field " + field_name + " is too long."
    if not isinstance(raw_value, (int, float, str)):
        return None, "The field " + field_name + " must be a number."

    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return None, "The field " + field_name + " must be a number."

    if not math.isfinite(number):
        return None, "The field " + field_name + " must be a normal finite number."
    if maximum is not None and abs(number) > float(maximum):
        return None, "The field " + field_name + " is outside the supported range."

    return number, ""


def read_whole_number(payload, field_name, minimum, maximum):
    """Read a bounded whole number without silently truncating fractions."""
    number, error_message = read_number(payload, field_name, maximum=maximum)
    if error_message != "":
        return None, error_message
    if not number.is_integer():
        return None, "The field " + field_name + " must be a whole number."
    integer_value = int(number)
    if integer_value < minimum or integer_value > maximum:
        return None, "The field " + field_name + " is outside the supported range."
    return integer_value, ""


def validate_snapshot(payload):
    """Validate one hospital snapshot and return the clean values plus warnings."""
    warnings = []

    if not isinstance(payload, dict):
        return None, "The request body must be a JSON object.", warnings

    # The hospital must be one of the identifiers in the configured dataset.
    hospital_id, error_message = read_whole_number(payload, "hospital_id", 1, 1_000_000_000)
    if error_message != "":
        return None, error_message, warnings

    known_hospitals = CLEAN_DATA["hospital_id"].unique().tolist()
    if hospital_id not in known_hospitals:
        return None, "Hospital " + str(hospital_id) + " does not exist in the dataset.", warnings

    # The timestamp must be readable.
    raw_timestamp = payload.get("timestamp", "")
    if not isinstance(raw_timestamp, str):
        return None, "The date and time field must be a text timestamp.", warnings
    raw_timestamp = raw_timestamp.strip()
    if raw_timestamp == "":
        return None, "The date and time field is empty.", warnings
    if len(raw_timestamp) > 64:
        return None, "The date and time field is too long.", warnings

    parsed_timestamp = pd.to_datetime(raw_timestamp, errors="coerce")
    if not isinstance(parsed_timestamp, pd.Timestamp) or pd.isna(parsed_timestamp):
        return None, "The date and time value could not be read.", warnings
    if parsed_timestamp.tzinfo is not None:
        return None, "The date and time must not include a timezone offset.", warnings

    # Category values must exist in the dataset.
    category_checks = [
        ["disaster_type", CATEGORY_OPTIONS["disaster_types"], "disaster type"],
        ["triage_level", CATEGORY_OPTIONS["triage_levels"], "triage level"],
        ["injury_type", CATEGORY_OPTIONS["injury_types"], "injury type"],
    ]

    clean_input = {}
    for check in category_checks:
        field_name = check[0]
        allowed_values = check[1]
        friendly_name = check[2]

        raw_value = payload.get(field_name, "")
        if not isinstance(raw_value, str):
            return None, "Please choose a valid " + friendly_name + ".", warnings
        raw_value = raw_value.strip()
        if raw_value == "":
            return None, "Please choose a " + friendly_name + ".", warnings
        if len(raw_value) > 100:
            return None, "The selected " + friendly_name + " is too long.", warnings
        if raw_value not in allowed_values:
            return None, "The selected " + friendly_name + " is not present in the dataset.", warnings
        clean_input[field_name] = raw_value

    # Every numeric input is read, checked and stored.
    for field_name in NUMERIC_INPUT_COLUMNS:
        number, error_message = read_number(
            payload,
            field_name,
            maximum=NUMERIC_INPUT_MAXIMUMS[field_name],
        )
        if error_message != "":
            return None, error_message, warnings

        if number < 0:
            return None, "The field " + FEATURE_LABELS[field_name] + " cannot be negative.", warnings

        if field_name in PERCENT_INPUT_COLUMNS and number > 1.0:
            return None, ("The field " + FEATURE_LABELS[field_name] +
                          " must arrive as a decimal rate between 0 and 1."), warnings

        clean_input[field_name] = number

    clean_input["hospital_id"] = hospital_id
    clean_input["timestamp"] = parsed_timestamp

    # Values outside the training range are accepted but they raise a warning.
    for field_name in NUMERIC_INPUT_COLUMNS:
        observed = TRAINING_RANGES[field_name]
        value = clean_input[field_name]
        if value < observed["min"] or value > observed["max"]:
            warnings.append(FEATURE_LABELS[field_name] +
                            " is outside the model's observed training range, so uncertainty may be higher.")

    # A timestamp outside the dataset period is also worth a clear warning.
    dataset_start = pd.to_datetime(DATASET_INFO["start_timestamp"])
    dataset_end = pd.to_datetime(DATASET_INFO["end_timestamp"])
    if parsed_timestamp < dataset_start or parsed_timestamp > dataset_end:
        warnings.append("The selected date and time is outside the dataset period, so uncertainty may be higher.")

    return clean_input, "", warnings


def validate_reserve(payload):
    """Validate the three emergency reserve values entered by the user."""
    if not isinstance(payload, dict):
        return None, "The reserve must be a JSON object."

    reserve = {}
    field_map = {
        "icu_beds": "Emergency ICU beds available",
        "ventilators": "Emergency ventilators available",
        "staff": "Emergency staff units available",
    }

    for field_name in field_map:
        number, error_message = read_whole_number(
            payload,
            field_name,
            0,
            MAX_RESERVE_UNITS,
        )
        if error_message != "":
            return None, error_message
        reserve[field_name] = number

    return reserve, ""


def validate_weights(payload):
    """Validate the four objective weights entered by the user."""
    if not isinstance(payload, dict):
        return None, "The objective weights must be a JSON object."

    weights = {}
    weight_fields = ["patient_safety", "overload_relief", "patient_demand", "incident_proximity"]

    for field_name in weight_fields:
        number, error_message = read_number(payload, field_name, maximum=MAX_OBJECTIVE_WEIGHT)
        if error_message != "":
            return None, error_message
        if number < 0:
            return None, "Objective weights cannot be negative."
        weights[field_name] = number

    return weights, ""


# =============================================================================
# SECTION 18: DATA-GROUNDED CHAT ASSISTANT
# This section answers questions with fixed rules and configured dataset values only.
# It is not a language model and it never calls an external AI service.
# =============================================================================

# Ready-made questions that the interface offers as clickable chips.
CHAT_SUGGESTIONS = [
    "What is in this dataset?",
    "How accurate is the model?",
    "Which hospital is under the most pressure?",
    "What does the resilience index mean?",
    "How does the allocation work?",
    "What are the limitations?",
]


def clean_chat_message(message_text):
    """Turn the user question into simple lowercase text for keyword matching."""
    lowered = str(message_text).lower().strip()

    # Punctuation is replaced by spaces so keywords are easier to find.
    simple_text = ""
    for character in lowered:
        if character.isalnum():
            simple_text = simple_text + character
        else:
            simple_text = simple_text + " "

    return " " + " ".join(simple_text.split()) + " "


def message_contains(message_text, keyword_list):
    """Return True when the question contains at least one of the keywords."""
    for keyword in keyword_list:
        if " " + keyword + " " in message_text:
            return True
    return False


def find_hospital_in_message(message_text):
    """Find a hospital number such as 'hospital 12' inside the question."""
    known_hospitals = CLEAN_DATA["hospital_id"].unique().tolist()

    # A bare number is only treated as a hospital when the word hospital is used.
    words = message_text.split()
    only_number = len(words) == 1 and words[0].isdigit()
    if not message_contains(message_text, ["hospital"]) and not only_number:
        return None

    for word in words:
        if word.isdigit():
            number = int(word)
            if number in known_hospitals:
                return number

    return None


def find_unknown_hospital_number(message_text):
    """Find a hospital number that was written but does not exist in the dataset."""
    if not message_contains(message_text, ["hospital"]):
        return None

    known_hospitals = CLEAN_DATA["hospital_id"].unique().tolist()
    for word in message_text.split():
        if word.isdigit():
            number = int(word)
            if number not in known_hospitals:
                return number

    return None


def answer_unknown_hospital(hospital_number):
    """Explain clearly that the requested hospital is not part of the dataset."""
    hospital_ids = [int(item["id"]) for item in CATEGORY_OPTIONS.get("hospitals", [])]
    details = [
        "The dataset contains " + str(DATASET_INFO.get("hospital_count", len(hospital_ids))) +
        " hospital identifier" + ("" if len(hospital_ids) == 1 else "s") + ".",
    ]
    if hospital_ids:
        details.append("Available identifiers: " + ", ".join(str(value) for value in hospital_ids) + ".")
        details.append("Try an available identifier, for example 'predict hospital " +
                       str(hospital_ids[0]) + "'.")
    else:
        details.append("No hospital identifiers are currently available.")
    answer = "Hospital " + str(hospital_number) + " does not exist in this dataset, so I cannot answer about it."
    return build_chat_reply(answer, details, "Source: list of configured dataset identifiers.", "unknown_hospital")


def predict_latest_for_hospital(hospital_id):
    """Predict outputs for the latest configured dataset record for one hospital."""
    hospital_rows = CLEAN_DATA[CLEAN_DATA["hospital_id"] == int(hospital_id)]
    latest_row = hospital_rows.sort_values("timestamp").iloc[-1]

    record = build_record_from_dataset_row(latest_row)
    predictions, feature_frame = predict_records([record])
    return record, predictions[0]


def rank_hospitals_by_pressure():
    """Rank every hospital by an equally weighted operational priority score."""
    records = build_hospital_scenarios(0, None)
    predictions, feature_frame = predict_records(records)

    equal_weights = normalise_weights({
        "patient_safety": 1.0,
        "overload_relief": 1.0,
        "patient_demand": 1.0,
        "incident_proximity": 1.0,
    })

    scored_rows = calculate_priority_scores(records, predictions, equal_weights)
    scored_rows.sort(key=get_priority_value, reverse=True)
    return scored_rows


def build_chat_reply(answer_text, detail_lines, source_note, intent_name):
    """Build the standard reply object that the interface knows how to display."""
    reply = {}
    reply["answer"] = answer_text
    reply["details"] = detail_lines
    reply["source_note"] = source_note
    reply["intent"] = intent_name
    reply["suggestions"] = CHAT_SUGGESTIONS
    return reply


def answer_about_dataset():
    """Answer questions about the size and the period of the dataset."""
    details = [
        "Records: " + str(DATASET_INFO["row_count"]) + " rows from " + str(DATASET_INFO["hospital_count"]) + " hospitals.",
        "Period: " + DATASET_INFO["start_timestamp"] + " to " + DATASET_INFO["end_timestamp"] + ".",
        "Latest dataset record: " + DATASET_INFO["latest_timestamp"] + ".",
        "Recorded capacity statuses: " + str(DATASET_INFO["stable_records"]) + " Stable, " +
        str(DATASET_INFO["warning_records"]) + " Warning, " + str(DATASET_INFO["high_risk_records"]) + " High Risk.",
        "Most common disaster type: " + DATASET_INFO["most_common_disaster_type"] + ".",
    ]
    answer = ("The planner reads one CSV file of timestamped hospital-crisis dataset records. "
              "It is a stored dataset, not a live connection to any hospital.")
    return build_chat_reply(answer, details, "Source: dataset overview calculated at startup.", "dataset")


def answer_about_model():
    """Answer questions about model quality, the time split and target leakage."""
    details = []
    for metric in REGRESSION_METRICS:
        details.append(metric["label"] + ": R2 " + str(round(metric["r2"], 3)) +
                       ", average error " + str(round(metric["mae"], 2)) + " " + metric["unit"] + ".")

    details.append("Capacity status accuracy: " + str(round(CLASSIFICATION_METRICS["accuracy"] * 100.0, 1)) +
                   "%, macro F1: " + str(round(CLASSIFICATION_METRICS["macro_f1"], 3)) + ".")
    details.append("Tested on " + str(SPLIT_INFO["test_rows"]) + " records from " +
                   SPLIT_INFO["test_start"] + " to " + SPLIT_INFO["test_end"] + ", which the model never saw.")
    details.append("The six output columns are never used as inputs, so the scores are not inflated by leakage.")

    finite_r2_values = [
        float(metric["r2"])
        for metric in REGRESSION_METRICS
        if math.isfinite(float(metric["r2"]))
    ]
    if finite_r2_values:
        r2_summary = ("Held-out regression R2 values range from " +
                      str(round(min(finite_r2_values), 3)) + " to " +
                      str(round(max(finite_r2_values), 3)) + " across " +
                      str(len(finite_r2_values)) + " target" +
                      ("" if len(finite_r2_values) == 1 else "s") + ".")
    else:
        r2_summary = "No finite held-out regression R2 value is available."

    classifier_summary = (
        "The held-out capacity classifier reports " +
        str(round(CLASSIFICATION_METRICS["accuracy"] * 100.0, 1)) +
        "% accuracy and macro F1 " +
        str(round(CLASSIFICATION_METRICS["macro_f1"], 3)) + "."
    )
    answer = ("Every score comes from the later chronological test period only. " +
              r2_summary + " " + classifier_summary)
    return build_chat_reply(answer, details, "Source: metrics measured on the chronological test set.", "model_quality")


def answer_about_resilience():
    """Explain the derived operational resilience index."""
    details = [
        "pressure = 0.35 x predicted overload risk + 0.25 x bed occupancy + 0.25 x ICU occupancy + 0.15 x equipment usage.",
        "resilience index = 100 x (1 - pressure), kept between 0 and 100.",
        "70 to 100 means a strong operational position.",
        "45 to 69.99 means pressured but manageable.",
        "Below 45 means severe operational pressure.",
    ]
    answer = ("The resilience index is a transparent summary built for this project. A higher number means more "
              "operational room. It is not a medically validated score.")
    return build_chat_reply(answer, details, "Source: fixed formula shown in the Results view.", "resilience_index")


def answer_about_overload():
    """Explain the overload risk output and the capacity status."""
    details = [
        "Overload risk is a value between 0 and 1 in the dataset, shown as a percentage in the interface.",
        "Capacity status comes from a separate classifier, not from a fixed overload threshold.",
        "The three recorded status labels in the dataset are Stable, Warning and High Risk.",
        "Model confidence is the probability the classifier gives to the status it chose.",
    ]
    answer = ("Overload risk describes how close a hospital is to operational overload. The capacity status is "
              "predicted separately, so the two can disagree.")
    return build_chat_reply(answer, details, "Source: dataset columns overload_risk_score and capacity_flag.", "overload")


def answer_about_allocation():
    """Explain the priority score and the constrained allocation method."""
    details = [
        "Priority score = 100 x weighted average of patient safety, overload relief, patient demand and incident proximity.",
        "The four weights are normalised on the server, so they do not have to total 100.",
        "Weighted need = rounded-up predicted requirement x (1 + priority score / 100).",
        "Each hospital first receives the whole part of its proportional share of your reserve.",
        "Leftover units go one at a time to the largest remaining fraction, then to the higher priority score.",
        "No hospital receives more than its estimated need, and the totals never exceed the reserve you entered.",
    ]
    answer = ("The planner shares only the emergency reserve that you type in. It never invents resources and it "
              "never claims to know the confirmed stock of any hospital.")
    return build_chat_reply(answer, details, "Source: transparent priority-based constrained allocation.", "allocation")


def answer_about_limitations():
    """Answer honesty questions about live data, the horizon and medical advice."""
    details = [
        "The configured CSV holds timestamped dataset records. Nothing here is a live hospital feed.",
        "The validated prediction horizon is two hours, so no long-term forecast is offered.",
        "The dataset has no total physical capacity, so an exact shortage cannot be calculated.",
        "Allocations refer only to the emergency reserve you enter.",
        "A lower-pressure hospital is a possible coordination candidate, not confirmed transfer capacity.",
        "This is decision support. It is not medical diagnosis or treatment advice.",
    ]
    answer = ("This is an operational decision-support prototype. Qualified hospital and emergency-management staff "
              "must confirm every number before acting on it.")
    return build_chat_reply(answer, details, "Source: fixed project limitations.", "limitations")


def answer_how_to_use():
    """Explain the workflow of the four planner steps."""
    details = [
        "Step 1 - Situation: choose a hospital, load its latest dataset record and adjust the values.",
        "Step 2 - Prediction: read the six result cards, the strategies and the decision points.",
        "Step 3 - Resources: type the reserve you really have, set the weights and build the allocation plan.",
        "Reference: the Resilience view shows weekly dataset trends and the Model view shows the test scores.",
    ]
    answer = "Work through the numbered steps in the left sidebar from top to bottom."
    return build_chat_reply(answer, details, "Source: application workflow.", "how_to_use")


def answer_about_hospital_record(hospital_id):
    """Report the latest configured dataset record for one hospital."""
    hospital_rows = CLEAN_DATA[CLEAN_DATA["hospital_id"] == int(hospital_id)]
    latest_row = hospital_rows.sort_values("timestamp").iloc[-1]
    record = build_record_from_dataset_row(latest_row)
    display = build_display_record(record)

    details = [
        "Recorded at: " + display["timestamp"] + ".",
        "Disaster type: " + display["disaster_type"] + ", triage level: " + display["triage_level"] +
        ", injury type: " + display["injury_type"] + ".",
        "Bed occupancy " + str(display["bed_occupancy_percent"]) + "%, ICU occupancy " +
        str(display["icu_occupancy_percent"]) + "%, equipment usage " + str(display["equipment_usage_percent"]) + "%.",
        "Ambulance arrivals " + str(display["ambulance_arrivals_per_hour"]) + " per hour, patient arrival rate " +
        str(display["patient_arrival_rate"]) + ".",
        "Doctors available " + str(display["doctor_available"]) + ", nurse-to-patient ratio " +
        str(display["nurse_to_patient_ratio"]) + ".",
        "Recorded capacity status in the dataset: " + str(latest_row[CLASSIFICATION_TARGET]) + ".",
    ]
    answer = "This is the latest dataset record for " + get_hospital_label(hospital_id) + "."
    return build_chat_reply(answer, details, "Source: one row of the configured CSV file.", "hospital_record")


def answer_about_hospital_prediction(hospital_id):
    """Predict outputs for one hospital from its latest configured dataset record."""
    record, prediction = predict_latest_for_hospital(hospital_id)
    resilience = calculate_resilience_index(prediction, record)

    details = [
        "Patients expected in the next 2 hours: " + str(int(round(prediction["predicted_patients_next_2h"]))) + ".",
        "ICU beds estimated: " + str(int(math.ceil(prediction["required_icu_beds"]))) + ".",
        "Ventilators estimated: " + str(int(math.ceil(prediction["required_ventilators"]))) + ".",
        "Staff units estimated: " + str(int(math.ceil(prediction["required_staff"]))) + ".",
        "Predicted overload risk: " + str(round(prediction["overload_risk_score"] * 100.0, 1)) + "%.",
        "Predicted capacity status: " + prediction["capacity_status"] + " with " +
        str(round(prediction["capacity_confidence"] * 100.0, 1)) + "% model confidence.",
        "Derived resilience index: " + str(resilience["index"]) + " out of 100 (" + resilience["status"] + ").",
    ]
    answer = ("Prediction for " + get_hospital_label(hospital_id) + ", based on its latest dataset record from " +
              pd.to_datetime(record["timestamp"]).strftime("%Y-%m-%d %H:%M") + ".")
    return build_chat_reply(answer, details, "Source: the trained models applied to one configured dataset record.", "hospital_prediction")


def answer_about_hospital_history(hospital_id):
    """Report weekly dataset trends for one hospital."""
    analysis = build_history_analysis(hospital_id)

    details = [
        "Overload risk trend: " + analysis["trends"]["overload_risk"]["direction"] + ".",
        "Bed occupancy trend: " + analysis["trends"]["bed_occupancy"]["direction"] + ".",
        "ICU occupancy trend: " + analysis["trends"]["icu_occupancy"]["direction"] + ".",
        "Observed overload risk: lowest " + str(analysis["summary"]["min_overload_risk_percent"]) + "%, average " +
        str(analysis["summary"]["avg_overload_risk_percent"]) + "%, highest " +
        str(analysis["summary"]["max_overload_risk_percent"]) + "%.",
        str(analysis["summary"]["high_risk_percent"]) + "% of its " + str(analysis["summary"]["record_count"]) +
        " records were High Risk.",
    ]
    answer = ("Weekly dataset trends for " + get_hospital_label(hospital_id) +
              ". These are recorded trends, not a long-term forecast.")
    return build_chat_reply(answer, details, "Source: weekly averages of configured CSV rows.", "hospital_history")


def answer_about_pressure_ranking():
    """Name the hospitals with the highest and the lowest operational pressure."""
    scored_rows = rank_hospitals_by_pressure()

    if not scored_rows:
        return build_chat_reply(
            "No hospital records are available to rank.",
            ["The ranking requires at least one configured dataset record."],
            "Source: configured dataset hospital records.",
            "pressure_ranking",
        )

    details = []
    top_count = min(3, len(scored_rows))
    for position in range(top_count):
        row = scored_rows[position]
        details.append(str(position + 1) + ". " + row["hospital_label"] + " - priority score " +
                       str(row["priority_score"]) + ", predicted status " + row["capacity_status"] +
                       ", predicted overload risk " + str(row["overload_risk_percent"]) + "%.")

    if len(scored_rows) > top_count:
        lowest_row = scored_rows[-1]
        details.append("Lowest modeled pressure: " + lowest_row["hospital_label"] +
                       " with a priority score of " + str(lowest_row["priority_score"]) +
                       " and a predicted status of " + lowest_row["capacity_status"] + ".")
    details.append("This ranking uses the latest dataset record of every hospital and four equal objective weights.")

    answer = ("Ranked by the multi-objective operational priority score, " + scored_rows[0]["hospital_label"] +
              " has the highest modeled pressure in this ranking.")
    source_note = ("Source: model predictions for " + str(len(scored_rows)) + " latest dataset " +
                   ("record." if len(scored_rows) == 1 else "records."))
    return build_chat_reply(answer, details, source_note, "pressure_ranking")


def answer_about_coordination(hospital_id):
    """List possible lower-pressure coordination candidates for one hospital."""
    scored_rows = rank_hospitals_by_pressure()
    candidates = find_coordination_candidates(scored_rows, hospital_id)

    details = []
    if len(candidates) == 0:
        details.append("No other hospital has lower predicted overload risk, lower ICU occupancy and lower bed "
                       "occupancy at the same time.")
    else:
        for candidate in candidates:
            details.append(candidate["hospital_label"] + " - predicted status " + candidate["capacity_status"] +
                           ", overload risk " + str(candidate["overload_risk_percent"]) + "%, ICU occupancy " +
                           str(candidate["icu_occupancy_percent"]) + "%, bed occupancy " +
                           str(candidate["bed_occupancy_percent"]) + "%.")

    details.append("Actual transfer feasibility requires verified capacity, transport, clinical and local operational "
                   "information that is not included in this dataset.")

    answer = "Possible lower-pressure coordination candidates for " + get_hospital_label(hospital_id) + "."
    return build_chat_reply(answer, details, "Source: predictions compared across all hospitals.", "coordination")


def answer_fallback():
    """Explain what the assistant can answer when the question is not understood."""
    details = [
        "The dataset: size, period, hospitals and recorded statuses.",
        "Model quality: R2, average error, accuracy, macro F1 and the time split.",
        "One hospital: try 'latest record for hospital 7' or 'predict hospital 12' or 'trends for hospital 5'.",
        "Comparisons: 'which hospital is under the most pressure' or 'coordination for hospital 3'.",
        "Meanings: resilience index, overload risk, capacity status, priority score.",
        "Honesty: limitations, the two-hour horizon and why this is not live data.",
    ]
    answer = ("I did not recognise that question. I answer with fixed rules from the dataset and the trained models, "
              "so I only cover these topics:")
    return build_chat_reply(answer, details, "Source: assistant help text.", "fallback")


def build_chat_answer(raw_message, selected_hospital_id):
    """Choose the right rule-based answer for the user question."""
    message_text = clean_chat_message(raw_message)

    # A hospital number in the question always wins over the selected hospital.
    hospital_id = find_hospital_in_message(message_text)
    if hospital_id is None:
        # A number that was written but does not exist must be reported, not ignored.
        unknown_number = find_unknown_hospital_number(message_text)
        if unknown_number is not None:
            return answer_unknown_hospital(unknown_number)
        hospital_id = selected_hospital_id

    # The most specific topics are checked first.
    if message_contains(message_text, ["hello", "hi", "hey", "help", "start", "begin", "workflow", "guide"]):
        return answer_how_to_use()

    if message_contains(message_text, ["limitation", "limitations", "live", "realtime", "trust", "medical",
                                       "advice", "safe", "horizon", "wrong", "certain"]):
        return answer_about_limitations()

    if message_contains(message_text, ["resilience"]):
        return answer_about_resilience()

    if message_contains(message_text, ["allocate", "allocation", "reserve", "priority", "weights", "distribute", "share"]):
        return answer_about_allocation()

    if message_contains(message_text, ["coordination", "coordinate", "transfer", "candidate", "candidates"]):
        if hospital_id is not None:
            return answer_about_coordination(hospital_id)
        return answer_about_allocation()

    if message_contains(message_text, ["worst", "most", "highest", "busiest", "rank", "ranking", "compare", "which"]):
        return answer_about_pressure_ranking()

    if message_contains(message_text, ["accuracy", "accurate", "r2", "mae", "f1", "model", "quality", "leakage",
                                       "leak", "score", "scores", "performance", "test", "reliable"]):
        return answer_about_model()

    if message_contains(message_text, ["history", "trend", "trends", "weekly", "worsening", "improving",
                                       "past", "worse", "better", "getting", "deteriorating", "recovering"]):
        if hospital_id is not None:
            return answer_about_hospital_history(hospital_id)

    if message_contains(message_text, ["record", "latest", "current", "now", "condition", "situation"]):
        if hospital_id is not None:
            return answer_about_hospital_record(hospital_id)

    if message_contains(message_text, ["predict", "prediction", "forecast", "expect", "expected", "need", "needs",
                                       "icu", "ventilator", "ventilators", "staff", "patients", "beds"]):
        if hospital_id is not None:
            return answer_about_hospital_prediction(hospital_id)

    if message_contains(message_text, ["overload", "capacity", "status", "stable", "warning", "risk"]):
        return answer_about_overload()

    if message_contains(message_text, ["dataset", "data", "rows", "records", "hospitals", "period", "csv", "size"]):
        return answer_about_dataset()

    # A bare hospital number is treated as a request for that hospital.
    if hospital_id is not None and message_contains(message_text, ["hospital"]):
        return answer_about_hospital_prediction(hospital_id)

    return answer_fallback()


# =============================================================================
# SECTION 19: OPTIONAL LANGUAGE MODEL HELPER
# This section only rewrites dataset and model values into clearer sentences.
# It never invents a value and the application works fully without an API key.
# =============================================================================

# The model is always told to use the supplied facts and nothing else.
GROUNDING_RULES = (
    "You are the writing assistant of a hospital crisis decision-support tool. "
    "You must only use the numbers and statements given to you in the CONTEXT block. "
    "Never invent a number, a hospital, a date or a source. "
    "If the CONTEXT does not contain the answer, say clearly that the planner does not have that information. "
    "Never claim the data is live, and never give medical diagnosis or treatment advice. "
    "Write in short, plain, professional English that a hospital manager can read quickly."
)


def log_internal_event(event_name, error=None, status_code=None):
    """Write a diagnostic event without secret values, URLs or request content."""
    safe_event = "".join(
        character for character in str(event_name)
        if character.isalnum() or character in ("_", "-")
    )[:80]
    message = "SERVER EVENT: " + (safe_event or "internal_error")
    if status_code is not None:
        message = message + " status=" + str(int(status_code))
    if error is not None:
        message = message + " type=" + type(error).__name__
    print(message)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent redirects so authorization never moves to another origin."""

    def redirect_request(self, request_object, file_pointer, code, message, headers, new_url):
        return None


class AIResponseTooLargeError(ValueError):
    """Raised when an AI service returns more data than this app accepts."""


def read_limited_ai_response(web_response):
    """Read at most MAX_AI_RESPONSE_BYTES from an external response."""
    content_length = web_response.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            # A malformed Content-Length is ignored; the bounded read still protects us.
            declared_length = None
        if declared_length is not None and declared_length > MAX_AI_RESPONSE_BYTES:
            raise AIResponseTooLargeError()

    response_bytes = web_response.read(MAX_AI_RESPONSE_BYTES + 1)
    if len(response_bytes) > MAX_AI_RESPONSE_BYTES:
        raise AIResponseTooLargeError()
    return response_bytes


def call_language_model(system_prompt, user_prompt):
    """Send one request to any OpenAI-compatible chat endpoint from the .env file."""
    settings = get_ai_settings()

    if not settings["enabled"]:
        return "", "The language model is switched off. Set AI_ENABLED=true in the .env file."

    if settings["configuration_error"] != "":
        log_internal_event("ai_configuration_invalid")
        return "", "The language model configuration is invalid. Check the server configuration."

    if settings["base_url"] == "":
        return "", "AI_BASE_URL is empty in the .env file."

    request_url = settings["base_url"].rstrip("/") + "/chat/completions"

    request_body = {
        "model": settings["model"],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    request_headers = {"Content-Type": "application/json"}

    # A local model server often needs no key, so the header is only added when set.
    if settings["api_key"] != "":
        request_headers["Authorization"] = "Bearer " + settings["api_key"]

    encoded_body = json.dumps(request_body).encode("utf-8")
    web_request = urllib.request.Request(request_url, data=encoded_body, headers=request_headers, method="POST")

    opener = urllib.request.build_opener(NoRedirectHandler())

    try:
        with opener.open(web_request, timeout=settings["timeout_seconds"]) as web_response:
            answer_bytes = read_limited_ai_response(web_response)
            answer_data = json.loads(answer_bytes.decode("utf-8"))

        message_text = answer_data["choices"][0]["message"]["content"]
        if message_text is None:
            return "", "The language model returned an empty answer."

        message_text = str(message_text).strip()
        if len(message_text) > 50_000:
            return "", "The language model answer was too large."
        return message_text, ""

    except urllib.error.HTTPError as error:
        log_internal_event("ai_http_error", status_code=error.code)
        return "", "The language model service answered with status " + str(error.code) + "."

    except urllib.error.URLError as error:
        log_internal_event("ai_connection_error", error=error)
        return "", "The language model service could not be reached. Check AI_BASE_URL in the .env file."

    except AIResponseTooLargeError as error:
        log_internal_event("ai_response_too_large", error=error)
        return "", "The language model answer was too large."

    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as error:
        log_internal_event("ai_response_format_error", error=error)
        return "", "The language model answer could not be read."

    except Exception as error:
        log_internal_event("ai_unexpected_error", error=error)
        return "", "The language model request failed."


def build_context_lines(fact_lines):
    """Join the grounded facts into one clearly marked context block."""
    context_text = "CONTEXT (the only facts you may use):\n"
    for line in fact_lines:
        context_text = context_text + "- " + str(line) + "\n"
    return context_text


def build_general_facts():
    """Collect the dataset and model facts that are useful for almost any question."""
    facts = []
    facts.append("Dataset rows: " + str(DATASET_INFO["row_count"]) + " covering " +
                 str(DATASET_INFO["hospital_count"]) + " hospitals.")
    facts.append("Dataset period: " + DATASET_INFO["start_timestamp"] + " to " + DATASET_INFO["end_timestamp"] + ".")
    facts.append("The configured data consists of timestamped CSV records, never a live hospital feed.")
    facts.append("Recorded statuses: " + str(DATASET_INFO["stable_records"]) + " Stable, " +
                 str(DATASET_INFO["warning_records"]) + " Warning, " +
                 str(DATASET_INFO["high_risk_records"]) + " High Risk.")

    for metric in REGRESSION_METRICS:
        facts.append("Model quality for " + metric["label"] + ": R2 " + str(round(metric["r2"], 3)) +
                     ", average error " + str(round(metric["mae"], 2)) + " " + metric["unit"] + ".")

    facts.append("Capacity classifier accuracy " + str(round(CLASSIFICATION_METRICS["accuracy"] * 100.0, 1)) +
                 "% and macro F1 " + str(round(CLASSIFICATION_METRICS["macro_f1"], 3)) +
                 ", measured on the future test period only.")
    facts.append("The validated prediction horizon is two hours. No longer forecast exists.")
    facts.append("The dataset has no total physical capacity, so an exact shortage cannot be calculated.")
    return facts


def improve_chat_answer(question_text, rule_reply):
    """Ask the language model to reword one rule-based answer, using its facts only."""
    fact_lines = []
    fact_lines.append("Rule-based answer: " + rule_reply["answer"])
    for detail in rule_reply["details"]:
        fact_lines.append(detail)

    # General facts let the model answer follow-up wording without inventing anything.
    for general_line in build_general_facts():
        fact_lines.append(general_line)

    user_prompt = (build_context_lines(fact_lines) +
                   "\nQUESTION: " + question_text +
                   "\n\nWrite the answer in at most four short sentences. "
                   "Do not repeat every bullet, because the exact numbers are already shown to the user "
                   "under your answer. Explain what the numbers mean for a hospital manager.")

    answer_text, error_message = call_language_model(GROUNDING_RULES, user_prompt)
    return answer_text, error_message


def build_briefing_facts(cards, capacity, resilience, record, pressure_factors, similar_cases, strategies):
    """Collect the prediction values that the briefing is allowed to use."""
    facts = []
    facts.append("Hospital: " + get_hospital_label(record["hospital_id"]) + ".")
    facts.append("Situation time: " + pd.to_datetime(record["timestamp"]).strftime("%Y-%m-%d %H:%M") + ".")
    facts.append("Disaster type: " + record["disaster_type"] + ", triage level: " + record["triage_level"] +
                 ", injury type: " + record["injury_type"] + ".")
    facts.append("Predicted patients in the next 2 hours: " + str(cards["patients_next_2h"]["value"]) +
                 " (likely model range " + str(cards["patients_next_2h"]["low"]) + " to " +
                 str(cards["patients_next_2h"]["high"]) + ").")
    facts.append("Predicted ICU beds: " + str(cards["icu_beds"]["value"]) + " (range " +
                 str(cards["icu_beds"]["low"]) + " to " + str(cards["icu_beds"]["high"]) + ").")
    facts.append("Predicted ventilators: " + str(cards["ventilators"]["value"]) + " (range " +
                 str(cards["ventilators"]["low"]) + " to " + str(cards["ventilators"]["high"]) + ").")
    facts.append("Predicted staff units: " + str(cards["staff"]["value"]) + " (range " +
                 str(cards["staff"]["low"]) + " to " + str(cards["staff"]["high"]) + ").")
    facts.append("Predicted overload risk: " + str(cards["overload_risk"]["value"]) + "%.")
    facts.append("Predicted capacity status: " + capacity["status"] + " with " +
                 str(capacity["confidence_percent"]) + "% model confidence.")
    facts.append("Derived resilience index: " + str(resilience["index"]) + " out of 100 (" + resilience["status"] + ").")
    facts.append("Current bed occupancy " + str(round(record["bed_occupancy_rate"] * 100.0, 1)) +
                 "%, ICU occupancy " + str(round(record["icu_occupancy_rate"] * 100.0, 1)) +
                 "%, equipment usage " + str(round(record["equipment_usage_rate"] * 100.0, 1)) + "%.")

    for factor in pressure_factors:
        facts.append("Pressure factor: " + factor["title"] + " " + factor["detail"])

    if similar_cases.get("count", 0) > 0:
        facts.append("In " + str(similar_cases["count"]) + " similar dataset records, " +
                     str(similar_cases["high_risk_percent"]) + "% ended High Risk and the average observed overload "
                     "risk was " + str(similar_cases["avg_overload_risk_percent"]) + "%.")

    for action in strategies["immediate_priorities"]:
        facts.append("Rule-based immediate action: " + action)

    facts.append("The staff estimate must not be compared with the number of available doctors, "
                 "because the dataset does not confirm the same unit.")
    return facts


def build_fallback_briefing(cards, capacity, resilience, strategies):
    """Write a clear briefing from the numbers when no language model is available."""
    summary = ("The model expects about " + str(cards["patients_next_2h"]["value"]) +
               " patients in the next two hours, with a predicted capacity status of " + capacity["status"] +
               " and a predicted overload risk of " + str(cards["overload_risk"]["value"]) + "%. " +
               "The derived resilience index is " + str(resilience["index"]) + " out of 100, described as " +
               resilience["status"].lower() + ". Estimated needs are " + str(cards["icu_beds"]["value"]) +
               " ICU beds, " + str(cards["ventilators"]["value"]) + " ventilators and " +
               str(cards["staff"]["value"]) + " staff units.")

    recommendations = []
    for action in strategies["immediate_priorities"]:
        recommendations.append(action)
    for action in strategies["next_two_hours"]:
        recommendations.append(action)

    return summary, recommendations[:5]


def build_ai_briefing(cards, capacity, resilience, record, pressure_factors, similar_cases, strategies):
    """Create the situation briefing, using the language model only when it is available."""
    fallback_summary, fallback_recommendations = build_fallback_briefing(cards, capacity, resilience, strategies)

    settings = get_ai_settings()
    briefing = {}
    briefing["ai_enabled"] = settings["enabled"]
    briefing["ai_used"] = False
    briefing["ai_error"] = ""
    briefing["model_name"] = settings["model"] if settings["enabled"] else ""
    briefing["summary"] = fallback_summary
    briefing["recommendations"] = fallback_recommendations
    briefing["source_note"] = ("Written from the prediction values by fixed rules. "
                               "Switch on AI_ENABLED in the .env file for a written briefing.")

    if not settings["enabled"]:
        return briefing

    fact_lines = build_briefing_facts(cards, capacity, resilience, record, pressure_factors, similar_cases, strategies)

    user_prompt = (build_context_lines(fact_lines) +
                   "\nTASK: write an operational briefing for the hospital manager.\n"
                   "Answer with valid JSON only, using exactly this shape:\n"
                   '{"summary": "three short sentences", "recommendations": ["action", "action", "action", "action"]}\n'
                   "Each recommendation must be one sentence, must come from the context, and must use careful "
                   "wording such as 'should be considered' or 'may help'. Do not promise any outcome.")

    answer_text, error_message = call_language_model(GROUNDING_RULES, user_prompt)

    if error_message != "":
        briefing["ai_error"] = error_message
        return briefing

    written_summary, written_recommendations = read_briefing_json(answer_text)

    if written_summary == "":
        briefing["ai_error"] = "The language model answer was not readable, so the rule-based briefing is shown."
        return briefing

    briefing["ai_used"] = True
    briefing["summary"] = written_summary
    if len(written_recommendations) > 0:
        briefing["recommendations"] = written_recommendations
    briefing["source_note"] = ("Worded by the language model " + settings["model"] +
                               " from the prediction values shown on this page. Every number stays from the models.")
    return briefing


def read_briefing_json(answer_text):
    """Read the JSON briefing that the language model returned, without crashing."""
    cleaned_text = answer_text.strip()

    # Some models wrap JSON in a markdown code fence, so the fence is removed first.
    if cleaned_text.startswith("```"):
        parts = cleaned_text.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{"):
                cleaned_text = stripped
                break

    try:
        parsed = json.loads(cleaned_text)
    except ValueError:
        # A small amount of surrounding prose is tolerated, but a valid JSON
        # non-object is never reinterpreted as an object hidden inside it.
        start_position = cleaned_text.find("{")
        end_position = cleaned_text.rfind("}")
        if start_position < 0 or end_position <= start_position:
            return "", []
        try:
            parsed = json.loads(cleaned_text[start_position:end_position + 1])
        except ValueError:
            return "", []

    if not isinstance(parsed, dict):
        return "", []

    summary_text = str(parsed.get("summary", "")).strip()
    if len(summary_text) > 2_000:
        summary_text = summary_text[:2_000].rstrip()

    recommendation_list = []
    raw_list = parsed.get("recommendations", [])
    if isinstance(raw_list, list):
        for item in raw_list:
            text_item = str(item).strip()
            if text_item != "":
                recommendation_list.append(text_item[:500].rstrip())

    return summary_text, recommendation_list[:6]


# =============================================================================
# SECTION 20: FLASK APPLICATION AND WEB ROUTES
# This section starts the whole pipeline once and then serves the web routes.
# It never returns a full exception trace to the browser.
# =============================================================================

def make_json_safe(value):
    """Turn numpy values, NaN and infinity into values that jsonify can handle."""
    if isinstance(value, dict):
        safe_dict = {}
        for key in value:
            safe_dict[str(key)] = make_json_safe(value[key])
        return safe_dict

    if isinstance(value, (list, tuple)):
        safe_list = []
        for item in value:
            safe_list.append(make_json_safe(item))
        return safe_list

    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M")

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    return value


def start_everything():
    """Run the complete startup pipeline once: load, clean, split, train, measure."""
    global CLEAN_DATA, TRAIN_DATA, TEST_DATA, LATEST_RECORDS, FEATURE_COLUMNS
    global REGRESSION_MODEL, CLASSIFICATION_MODEL
    global REGRESSION_METRICS, CLASSIFICATION_METRICS, FEATURE_IMPORTANCES
    global SPLIT_INFO, DATASET_INFO, TRAINING_RANGES, CATEGORY_OPTIONS
    global MODEL_READY, STARTUP_ERROR

    dataset_path = get_dataset_path()
    raw_data = load_dataset(dataset_path)

    # The schema check must explain exactly which columns are missing.
    missing_columns = validate_columns(raw_data)
    if len(missing_columns) > 0:
        raise ValueError("The dataset is missing these required columns: " + ", ".join(missing_columns))

    # Retain only the documented schema so unexpected sensitive columns do not
    # remain in long-lived global DataFrames.
    raw_data = raw_data[REQUIRED_COLUMNS].copy()

    clean = clean_dataset(raw_data)
    if len(clean) == 0:
        raise ValueError("No usable rows remained after cleaning the dataset.")

    train, test = split_by_time(clean)
    training_medians = fill_missing_numeric_values(train, test, clean)

    CLEAN_DATA = clean
    TRAIN_DATA = train
    TEST_DATA = test
    TRAINING_RANGES = build_training_ranges(train, training_medians)
    SPLIT_INFO = build_split_info(train, test)
    DATASET_INFO = build_dataset_overview(clean)
    CATEGORY_OPTIONS = build_category_options(clean)

    # The latest configured dataset record for every hospital is used by the allocation report.
    LATEST_RECORDS = clean.sort_values("timestamp").groupby("hospital_id").tail(1)
    LATEST_RECORDS = LATEST_RECORDS.sort_values("hospital_id").reset_index(drop=True)

    x_train = encode_training_features(train)
    FEATURE_COLUMNS = list(x_train.columns)
    x_test = encode_other_features(test)

    y_train_regression = train[REGRESSION_TARGETS]
    y_test_regression = test[REGRESSION_TARGETS]
    y_train_classification = train[CLASSIFICATION_TARGET]
    y_test_classification = test[CLASSIFICATION_TARGET]

    REGRESSION_MODEL = train_regression_model(x_train, y_train_regression)
    CLASSIFICATION_MODEL = train_classification_model(x_train, y_train_classification)

    REGRESSION_METRICS = calculate_regression_metrics(REGRESSION_MODEL, x_test, y_test_regression)
    CLASSIFICATION_METRICS = calculate_classification_metrics(CLASSIFICATION_MODEL, x_test, y_test_classification)
    FEATURE_IMPORTANCES = calculate_feature_importances(REGRESSION_MODEL, FEATURE_COLUMNS)

    MODEL_READY = True
    STARTUP_ERROR = ""


def run_startup_self_check():
    """Run the startup pipeline safely and print a short summary in the console."""
    global MODEL_READY, STARTUP_ERROR

    try:
        start_everything()
        print("=" * 70)
        print("CityCare Recovery Planner - startup summary")
        print("Dataset rows      :", DATASET_INFO["row_count"])
        print("Hospitals         :", DATASET_INFO["hospital_count"])
        print("Training rows     :", SPLIT_INFO["train_rows"])
        print("Testing rows      :", SPLIT_INFO["test_rows"])
        print("Shared timestamps :", SPLIT_INFO["shared_timestamps"])
        print("Model ready       :", MODEL_READY)
        print("=" * 70)
    except Exception as error:
        MODEL_READY = False
        STARTUP_ERROR = PUBLIC_STARTUP_ERROR
        log_internal_event("startup_failed", error=error)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BODY_BYTES


@app.after_request
def add_security_headers(response):
    """Add browser hardening headers and prevent API response caching."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; img-src 'self' data:; font-src 'self'; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'",
    )
    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

# The whole pipeline runs one single time when the application starts.
run_startup_self_check()


@app.route("/")
def home_page():
    """Serve the single dashboard page."""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Return the startup state, dataset overview and held-out test metrics."""
    response = {}
    response["ready"] = MODEL_READY
    response["startup_error"] = "" if MODEL_READY else PUBLIC_STARTUP_ERROR
    response["methodology_label"] = METHODOLOGY_LABEL
    response["model_names"] = {
        "regression": "RandomForestRegressor with multi-output targets",
        "classification": "RandomForestClassifier for the capacity status",
    }

    # The key itself is never sent to the browser, only whether the helper is on.
    ai_settings = get_ai_settings()
    response["ai"] = {
        "enabled": ai_settings["enabled"],
        "available": ai_settings["enabled"] and ai_settings["configuration_error"] == "",
        "model": ai_settings["model"] if ai_settings["enabled"] else "",
        "configuration_valid": ai_settings["configuration_error"] == "",
        "note": ("The language model only rewrites values that the trained models produced. "
                  "Every number stays from the dataset and the forests."),
    }

    if not MODEL_READY:
        return jsonify(make_json_safe(response)), 503

    response["dataset"] = DATASET_INFO
    response["split"] = SPLIT_INFO
    response["regression_metrics"] = REGRESSION_METRICS
    response["classification_metrics"] = CLASSIFICATION_METRICS
    response["feature_importances"] = FEATURE_IMPORTANCES
    response["excluded_input_columns"] = OUTPUT_COLUMNS
    return jsonify(make_json_safe(response)), 200


@app.route("/api/options")
def api_options():
    """Return configured dataset options and observed training ranges."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    response = {}
    response["hospitals"] = CATEGORY_OPTIONS["hospitals"]
    response["disaster_types"] = CATEGORY_OPTIONS["disaster_types"]
    response["triage_levels"] = CATEGORY_OPTIONS["triage_levels"]
    response["injury_types"] = CATEGORY_OPTIONS["injury_types"]
    response["capacity_statuses"] = CATEGORY_OPTIONS["capacity_statuses"]
    response["numeric_ranges"] = TRAINING_RANGES
    response["latest_timestamp"] = DATASET_INFO["latest_timestamp"]
    return jsonify(make_json_safe(response)), 200


@app.route("/api/hospital/<int:hospital_id>/latest")
def api_hospital_latest(hospital_id):
    """Return the latest configured dataset record for one hospital in interface units."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    hospital_rows = CLEAN_DATA[CLEAN_DATA["hospital_id"] == int(hospital_id)]
    if len(hospital_rows) == 0:
        return jsonify({"error": "Hospital " + str(hospital_id) + " does not exist in the dataset."}), 404

    latest_row = hospital_rows.sort_values("timestamp").iloc[-1]
    record = build_record_from_dataset_row(latest_row)

    response = build_display_record(record)
    response["record_label"] = "Latest dataset record"
    return jsonify(make_json_safe(response)), 200


@app.route("/api/history/<int:hospital_id>")
def api_history(hospital_id):
    """Return weekly dataset values and trend directions for one hospital."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    analysis = build_history_analysis(hospital_id)
    if analysis is None:
        return jsonify({"error": "Hospital " + str(hospital_id) + " does not exist in the dataset."}), 404

    return jsonify(make_json_safe(analysis)), 200


@app.route("/api/predict", methods=["POST"])
def api_predict():
    """Predict the outputs for one hospital snapshot and build the recovery plan."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "The request body must be a JSON object."}), 400

    # An unknown hospital is a missing resource, so it answers with 404.
    hospital_id, hospital_error = read_whole_number(payload, "hospital_id", 1, 1_000_000_000)
    if hospital_error != "":
        return jsonify({"error": hospital_error}), 400
    if hospital_id not in CLEAN_DATA["hospital_id"].unique().tolist():
        return jsonify({"error": "The requested hospital does not exist in the dataset."}), 404

    clean_input, error_message, warnings = validate_snapshot(payload)
    if error_message != "":
        return jsonify({"error": error_message}), 400

    try:
        record = build_record_from_input(clean_input)

        predictions, feature_frame = predict_records([record])
        prediction = predictions[0]
        ranges = calculate_prediction_ranges(feature_frame)
        cards = build_prediction_cards(prediction, ranges)

        resilience = calculate_resilience_index(prediction, record)
        pressure_factors = build_pressure_factors(record)
        similar_cases = find_similar_cases(record)

        # Every hospital is predicted as well, so coordination candidates are dataset-backed.
        scenario_records = build_hospital_scenarios(record["hospital_id"], record)
        scenario_predictions, ignored_frame = predict_records(scenario_records)
        equal_weights = normalise_weights({
            "patient_safety": 1.0,
            "overload_relief": 1.0,
            "patient_demand": 1.0,
            "incident_proximity": 1.0,
        })
        scored_rows = calculate_priority_scores(scenario_records, scenario_predictions, equal_weights)
        coordination_candidates = find_coordination_candidates(scored_rows, record["hospital_id"])

        strategies = create_recovery_strategies(cards, prediction["capacity_status"], resilience, record, coordination_candidates)
        recommendations = create_decision_recommendations(cards, prediction["capacity_status"], resilience, similar_cases, record)

        response = {}
        response["hospital_id"] = record["hospital_id"]
        response["hospital_label"] = get_hospital_label(record["hospital_id"])
        response["cleaned_input"] = build_display_record(record)
        response["warnings"] = warnings
        response["predictions"] = cards
        response["capacity"] = {
            "status": prediction["capacity_status"],
            "confidence_percent": round(float(prediction["capacity_confidence"]) * 100.0, 1),
            "probabilities": prediction["capacity_probabilities"],
        }
        response["resilience"] = resilience
        response["pressure_factors"] = pressure_factors
        response["similar_cases"] = similar_cases
        response["recovery_strategies"] = strategies
        response["decision_recommendations"] = recommendations
        response["coordination_candidates"] = coordination_candidates
        response["coordination_note"] = ("Actual transfer feasibility requires verified capacity, transport, clinical and "
                                         "local operational information that is not included in this dataset.")
        response["pressure_factor_note"] = "Current factors associated with higher operational pressure."

        return jsonify(make_json_safe(response)), 200

    except Exception as error:
        log_internal_event("prediction_failed", error=error)
        return jsonify({"error": "The prediction could not be completed because of an internal server error."}), 500


@app.route("/api/allocate", methods=["POST"])
def api_allocate():
    """Rank every hospital and share the entered emergency reserve between them."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "The request body must be a JSON object."}), 400

    reserve, error_message = validate_reserve(payload.get("reserve"))
    if error_message != "":
        return jsonify({"error": error_message}), 400

    weights, error_message = validate_weights(payload.get("weights"))
    if error_message != "":
        return jsonify({"error": error_message}), 400

    selected_hospital_id, error_message = read_whole_number(
        payload,
        "selected_hospital_id",
        1,
        1_000_000_000,
    )
    if error_message != "":
        return jsonify({"error": error_message}), 400

    if selected_hospital_id not in CLEAN_DATA["hospital_id"].unique().tolist():
        return jsonify({"error": "The requested hospital does not exist in the dataset."}), 404

    selected_record = None
    snapshot_warnings = []

    # The user may apply the current form scenario to the selected hospital only.
    use_scenario = payload.get("use_current_scenario", False)
    if not isinstance(use_scenario, bool):
        return jsonify({"error": "The field use_current_scenario must be true or false."}), 400
    if use_scenario:
        snapshot = payload.get("snapshot", None)
        if snapshot is None:
            return jsonify({"error": "The current form scenario was requested but no snapshot was sent."}), 400

        clean_input, error_message, snapshot_warnings = validate_snapshot(snapshot)
        if error_message != "":
            return jsonify({"error": error_message}), 400
        if int(clean_input["hospital_id"]) != selected_hospital_id:
            return jsonify({"error": "The snapshot hospital does not match the selected hospital."}), 400

        selected_record = build_record_from_input(clean_input)

    try:
        normalised_weights = normalise_weights(weights)

        scenario_records = build_hospital_scenarios(selected_hospital_id, selected_record)
        scenario_predictions, ignored_frame = predict_records(scenario_records)
        scored_rows = calculate_priority_scores(scenario_records, scenario_predictions, normalised_weights)

        plan = build_allocation_plan(scored_rows, reserve)
        coordination_candidates = find_coordination_candidates(scored_rows, selected_hospital_id)

        selected_summary = None
        for row in plan["rows"]:
            if int(row["hospital_id"]) == selected_hospital_id:
                selected_summary = row

        methodology_warnings = []
        methodology_warnings.append("These numbers describe the recommended allocation of the entered emergency reserve only. "
                                    "They are not the existing resources of any hospital.")
        methodology_warnings.append("The dataset does not contain total physical hospital capacity, so an exact shortage cannot be calculated.")
        methodology_warnings.append("The estimated staff requirement is not compared with the number of available doctors, "
                                    "because the dataset does not confirm that both values use the same unit.")
        if reserve["icu_beds"] == 0 and reserve["ventilators"] == 0 and reserve["staff"] == 0:
            methodology_warnings.append("Every reserve value is zero, so the table shows the priority ranking only. "
                                        "Enter the currently available reserve to distribute resources.")
        for warning_text in snapshot_warnings:
            methodology_warnings.append(warning_text)

        rounded_weights = {}
        for key in normalised_weights:
            rounded_weights[key] = round(normalised_weights[key], 4)

        response = {}
        response["method"] = ALLOCATION_METHOD_LABEL
        response["method_explanation"] = ("Each hospital receives a weighted need equal to its rounded-up predicted requirement "
                                          "multiplied by (1 + priority score / 100). Every hospital first receives the whole part "
                                          "of its proportional share, and the leftover units are given one at a time to the largest "
                                          "remaining fraction and then to the higher priority score. No hospital receives more than "
                                          "its estimated need, and the totals can never exceed the entered reserve.")
        response["priority_formula"] = ("priority score = 100 x (weight1 x patient safety + weight2 x overload relief + "
                                        "weight3 x patient demand + weight4 x incident proximity), using weights that add up to 1.")
        response["weights_entered"] = weights
        response["normalized_weights"] = rounded_weights
        response["selected_hospital_id"] = selected_hospital_id
        response["selected_hospital_label"] = get_hospital_label(selected_hospital_id)
        response["used_current_scenario"] = use_scenario
        response["rows"] = plan["rows"]
        response["reserve_entered"] = reserve
        response["total_allocated"] = plan["total_allocated"]
        response["remaining_reserve"] = plan["remaining_reserve"]
        response["selected_hospital_summary"] = selected_summary
        response["coordination_candidates"] = coordination_candidates
        response["coordination_note"] = ("Actual transfer feasibility requires verified capacity, transport, clinical and "
                                         "local operational information that is not included in this dataset.")
        response["methodology_warnings"] = methodology_warnings
        response["hospital_count"] = len(plan["rows"])

        return jsonify(make_json_safe(response)), 200

    except Exception as error:
        log_internal_event("allocation_failed", error=error)
        return jsonify({"error": "The allocation plan could not be completed because of an internal server error."}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Answer one user question with fixed rules and configured dataset values."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "The request body must be a JSON object."}), 400

    raw_message = payload.get("message", "")
    if not isinstance(raw_message, str):
        return jsonify({"error": "The question must be text."}), 400
    raw_message = raw_message.strip()
    if raw_message == "":
        return jsonify({"error": "Please type a question before sending it."}), 400
    if len(raw_message) > 400:
        return jsonify({"error": "Please keep the question shorter than 400 characters."}), 400

    # The selected hospital is optional and only used when no number is written.
    selected_hospital_id = None
    if payload.get("selected_hospital_id", None) is not None:
        selected_hospital_id, hospital_error = read_whole_number(
            payload,
            "selected_hospital_id",
            1,
            1_000_000_000,
        )
        if hospital_error != "":
            return jsonify({"error": hospital_error}), 400
        if selected_hospital_id not in CLEAN_DATA["hospital_id"].unique().tolist():
            return jsonify({"error": "The requested hospital does not exist in the dataset."}), 404

    try:
        reply = build_chat_answer(raw_message, selected_hospital_id)
        reply["question"] = raw_message

        # The rule-based answer is always kept, so the grounded values stay visible.
        settings = get_ai_settings()
        reply["ai_enabled"] = settings["enabled"]
        reply["ai_used"] = False
        reply["ai_error"] = ""
        reply["rule_answer"] = reply["answer"]

        if settings["enabled"]:
            written_answer, ai_error = improve_chat_answer(raw_message, reply)
            if written_answer != "":
                reply["answer"] = written_answer
                reply["ai_used"] = True
                reply["source_note"] = (reply["source_note"] +
                                        " Worded by " + settings["model"] + " from these values only.")
            else:
                reply["ai_error"] = ai_error

        return jsonify(make_json_safe(reply)), 200

    except Exception as error:
        log_internal_event("chat_failed", error=error)
        return jsonify({"error": "The assistant could not answer because of an internal server error."}), 500


@app.route("/api/briefing", methods=["POST"])
def api_briefing():
    """Write a short situation briefing from freshly recalculated predictions."""
    if not MODEL_READY:
        return jsonify({"error": "The dataset or the models are not ready. Check the model status message."}), 503

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "The request body must be a JSON object."}), 400

    # An unknown hospital is a missing resource, so it answers with 404.
    hospital_id, hospital_error = read_whole_number(payload, "hospital_id", 1, 1_000_000_000)
    if hospital_error != "":
        return jsonify({"error": hospital_error}), 400
    if hospital_id not in CLEAN_DATA["hospital_id"].unique().tolist():
        return jsonify({"error": "The requested hospital does not exist in the dataset."}), 404

    clean_input, error_message, warnings = validate_snapshot(payload)
    if error_message != "":
        return jsonify({"error": error_message}), 400

    try:
        # The briefing never trusts numbers from the browser, it recalculates them.
        record = build_record_from_input(clean_input)

        predictions, feature_frame = predict_records([record])
        prediction = predictions[0]
        ranges = calculate_prediction_ranges(feature_frame)
        cards = build_prediction_cards(prediction, ranges)

        resilience = calculate_resilience_index(prediction, record)
        pressure_factors = build_pressure_factors(record)
        similar_cases = find_similar_cases(record)

        capacity = {
            "status": prediction["capacity_status"],
            "confidence_percent": round(float(prediction["capacity_confidence"]) * 100.0, 1),
        }

        strategies = create_recovery_strategies(cards, prediction["capacity_status"], resilience, record, [])

        briefing = build_ai_briefing(cards, capacity, resilience, record,
                                     pressure_factors, similar_cases, strategies)
        briefing["hospital_label"] = get_hospital_label(record["hospital_id"])
        briefing["warnings"] = warnings

        return jsonify(make_json_safe(briefing)), 200

    except Exception as error:
        log_internal_event("briefing_failed", error=error)
        return jsonify({"error": "The briefing could not be created because of an internal server error."}), 500


@app.errorhandler(404)
def handle_not_found(error):
    """Return a clear JSON message for unknown API paths."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "This API path does not exist."}), 404
    return render_template("index.html"), 404


@app.errorhandler(500)
def handle_server_error(error):
    """Return a short JSON message instead of an exception trace."""
    log_internal_event("unhandled_request_error", error=error)
    return jsonify({"error": "An unexpected server error happened."}), 500


@app.errorhandler(413)
def handle_request_too_large(error):
    """Return a bounded JSON response when a request exceeds the body limit."""
    return jsonify({"error": "The request body is too large."}), 413


# =============================================================================
# SECTION 21: RUN THE SERVER
# This section only starts the Flask development server with the .env settings.
# It never enables debug mode by itself and never prints secret values.
# =============================================================================

if __name__ == "__main__":
    server_port = get_port_number()
    server_host = get_host_address()
    debug_mode = get_safe_debug_flag(server_host)

    print("Starting the CityCare Recovery Planner on", server_host, "port", server_port)
    print("Debug mode:", debug_mode)

    # The reloader is switched off so the models are never trained twice.
    app.run(host=server_host, port=server_port, debug=debug_mode, use_reloader=False)
