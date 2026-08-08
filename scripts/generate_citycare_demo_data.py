"""Generate an independently created synthetic CityCare demonstration dataset.

This module does not copy, transform, sample, or otherwise derive from the
original or supplied competition dataset.  Its records are deterministic demo
scenarios created solely by the formulas in this file.  They do not describe,
model, or represent any real hospital, patient, incident, or health system and
must not be used for clinical or operational decisions.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

COLUMNS = [
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

DISASTER_TYPES = (
    "Earthquake",
    "Epidemic",
    "Explosion",
    "Flood",
    "Mass Accident",
)
TRIAGE_LEVELS = ("Minor", "Urgent", "Critical")
INJURY_TYPES = (
    "Burn",
    "Fracture",
    "Head Injury",
    "Internal Bleeding",
    "Trauma",
)
CAPACITY_FLAGS = ("Stable", "Warning", "High Risk")

HOSPITAL_COUNT = 30
START_TIMESTAMP = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
DEFAULT_OUTPUT = Path("data") / "citycare_demo_dataset.csv"
DEFAULT_ROWS = 6_000
DEFAULT_SEED = 42
MIN_ROWS = 300
MAX_ROWS = 200_000
MIN_SEED = 0
MAX_SEED = (2**32) - 1


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _bounded_integer(value: float, lower: int, upper: int) -> int:
    return max(lower, min(upper, round(value)))


def _validate_generation_values(row_count: int, seed: int) -> None:
    if not MIN_ROWS <= row_count <= MAX_ROWS:
        raise ValueError(
            f"row_count must be between {MIN_ROWS} and {MAX_ROWS} inclusive"
        )
    if not MIN_SEED <= seed <= MAX_SEED:
        raise ValueError(f"seed must be between {MIN_SEED} and {MAX_SEED} inclusive")


def generate_rows(row_count: int, seed: int) -> Iterator[dict[str, object]]:
    """Yield deterministic, bounded synthetic rows in chronological order."""

    _validate_generation_values(row_count, seed)
    # Determinism is intentional; this generator creates demo data, not secrets.
    random_source = random.Random(seed)  # nosec B311

    for row_index in range(row_count):
        timestamp_index = row_index // HOSPITAL_COUNT
        hospital_id = (row_index % HOSPITAL_COUNT) + 1
        timestamp = START_TIMESTAMP + timedelta(hours=timestamp_index)

        # Each timestamp contains all three pressure bands across the hospitals.
        # This guarantees every chronological train/test partition has all three
        # labels without borrowing any structure from the supplied dataset.
        pressure_band = (hospital_id + timestamp_index) % len(CAPACITY_FLAGS)
        base_pressure = (0.24, 0.56, 0.84)[pressure_band]
        daily_cycle = 0.025 * math.sin((2.0 * math.pi * timestamp.hour) / 24.0)
        hospital_effect = ((hospital_id % 7) - 3) * 0.006
        pressure = _clamp(
            base_pressure
            + daily_cycle
            + hospital_effect
            + random_source.uniform(-0.025, 0.025),
            0.12,
            0.95,
        )

        disaster_type = DISASTER_TYPES[
            (hospital_id + (timestamp_index // 6)) % len(DISASTER_TYPES)
        ]
        triage_level = TRIAGE_LEVELS[
            (pressure_band + (timestamp_index // 12)) % len(TRIAGE_LEVELS)
        ]
        injury_type = INJURY_TYPES[
            ((2 * hospital_id) + timestamp_index) % len(INJURY_TYPES)
        ]

        incident_distance_km = _clamp(
            random_source.triangular(0.5, 60.0, 18.0) - (3.0 * pressure),
            0.5,
            60.0,
        )
        ambulance_arrivals_per_hour = _bounded_integer(
            2.0 + (16.0 * pressure) + random_source.gauss(0.0, 1.4), 1, 30
        )
        patient_arrival_rate = _clamp(
            7.0
            + (43.0 * pressure)
            + (0.35 * ambulance_arrivals_per_hour)
            + random_source.gauss(0.0, 2.2),
            5.0,
            75.0,
        )

        injury_time_adjustment = {
            "Burn": 12.0,
            "Fracture": 4.0,
            "Head Injury": 16.0,
            "Internal Bleeding": 20.0,
            "Trauma": 9.0,
        }[injury_type]
        avg_treatment_time_min = _clamp(
            24.0
            + (102.0 * pressure)
            + injury_time_adjustment
            + random_source.gauss(0.0, 5.0),
            20.0,
            180.0,
        )

        triage_risk_adjustment = {
            "Minor": 0.0,
            "Urgent": 0.035,
            "Critical": 0.075,
        }[triage_level]
        mortality_risk_score = _clamp(
            0.01
            + (0.33 * pressure)
            + triage_risk_adjustment
            + random_source.uniform(-0.012, 0.012),
            0.01,
            0.65,
        )
        bed_occupancy_rate = _clamp(
            0.34
            + (0.59 * pressure)
            + hospital_effect
            + random_source.uniform(-0.025, 0.025),
            0.30,
            0.98,
        )
        icu_occupancy_rate = _clamp(
            0.26
            + (0.63 * pressure)
            + hospital_effect
            + random_source.uniform(-0.025, 0.025),
            0.22,
            0.98,
        )
        equipment_usage_rate = _clamp(
            0.30
            + (0.60 * pressure)
            + random_source.uniform(-0.025, 0.025),
            0.25,
            0.98,
        )
        nurse_to_patient_ratio = _clamp(
            0.30 - (0.18 * pressure) + random_source.uniform(-0.012, 0.012),
            0.08,
            0.32,
        )
        doctor_available = _bounded_integer(
            43.0
            - (18.0 * pressure)
            + (hospital_effect * 25.0)
            + random_source.gauss(0.0, 1.8),
            8,
            48,
        )

        predicted_patients_next_2h = _bounded_integer(
            (1.55 * patient_arrival_rate)
            + (0.55 * ambulance_arrivals_per_hour)
            + random_source.gauss(0.0, 2.0),
            8,
            140,
        )
        critical_adjustment = 0.05 if triage_level == "Critical" else 0.0
        required_icu_beds = _bounded_integer(
            predicted_patients_next_2h
            * (0.07 + (0.15 * pressure) + critical_adjustment)
            + random_source.uniform(-0.7, 0.7),
            1,
            50,
        )
        required_ventilators = _bounded_integer(
            required_icu_beds
            * (0.22 + (0.50 * mortality_risk_score))
            + random_source.uniform(-0.4, 0.4),
            0,
            required_icu_beds,
        )
        required_staff = _bounded_integer(
            predicted_patients_next_2h * (0.22 + (0.16 * pressure))
            + random_source.uniform(-1.0, 1.0),
            3,
            80,
        )

        # Separated baselines keep all three labels present while the measured
        # pressures add realistic within-class variation.
        overload_risk_score = _clamp(
            (0.32, 0.60, 0.84)[pressure_band]
            + (0.06 * (bed_occupancy_rate - 0.65))
            + (0.05 * (icu_occupancy_rate - 0.65))
            + random_source.uniform(-0.018, 0.018),
            0.08,
            0.98,
        )
        if overload_risk_score < 0.48:
            capacity_flag = "Stable"
        elif overload_risk_score < 0.72:
            capacity_flag = "Warning"
        else:
            capacity_flag = "High Risk"

        yield {
            "hospital_id": hospital_id,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "disaster_type": disaster_type,
            "incident_distance_km": round(incident_distance_km, 3),
            "ambulance_arrivals_per_hour": ambulance_arrivals_per_hour,
            "patient_arrival_rate": round(patient_arrival_rate, 3),
            "triage_level": triage_level,
            "injury_type": injury_type,
            "avg_treatment_time_min": round(avg_treatment_time_min, 3),
            "mortality_risk_score": round(mortality_risk_score, 5),
            "bed_occupancy_rate": round(bed_occupancy_rate, 5),
            "icu_occupancy_rate": round(icu_occupancy_rate, 5),
            "equipment_usage_rate": round(equipment_usage_rate, 5),
            "nurse_to_patient_ratio": round(nurse_to_patient_ratio, 5),
            "doctor_available": doctor_available,
            "predicted_patients_next_2h": predicted_patients_next_2h,
            "required_icu_beds": required_icu_beds,
            "required_ventilators": required_ventilators,
            "required_staff": required_staff,
            "overload_risk_score": round(overload_risk_score, 5),
            "capacity_flag": capacity_flag,
        }


def write_dataset(
    output_path: Path, row_count: int, seed: int, *, force: bool = False
) -> None:
    """Write synthetic rows, refusing an existing destination by default."""

    _validate_generation_values(row_count, seed)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    open_mode = "w" if force else "x"

    with output_path.open(open_mode, newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(generate_rows(row_count, seed))


def _bounded_rows(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("rows must be a whole number") from error
    if not MIN_ROWS <= parsed <= MAX_ROWS:
        raise argparse.ArgumentTypeError(
            f"rows must be between {MIN_ROWS} and {MAX_ROWS}"
        )
    return parsed


def _bounded_seed(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("seed must be a whole number") from error
    if not MIN_SEED <= parsed <= MAX_SEED:
        raise argparse.ArgumentTypeError(
            f"seed must be between {MIN_SEED} and {MAX_SEED}"
        )
    return parsed


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic synthetic CityCare demo scenarios that do not "
            "represent real hospitals or patients."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="output CSV path (default: data/citycare_demo_dataset.csv)",
    )
    parser.add_argument(
        "--rows",
        type=_bounded_rows,
        default=DEFAULT_ROWS,
        help=f"number of rows ({MIN_ROWS}-{MAX_ROWS}; default: {DEFAULT_ROWS})",
    )
    parser.add_argument(
        "--seed",
        type=_bounded_seed,
        default=DEFAULT_SEED,
        help=f"deterministic seed ({MIN_SEED}-{MAX_SEED}; default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output file",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = build_argument_parser()
    options = parser.parse_args(arguments)

    try:
        write_dataset(
            options.output,
            options.rows,
            options.seed,
            force=options.force,
        )
    except FileExistsError:
        print(
            "Refusing to overwrite an existing output file; pass --force to replace it.",
            file=sys.stderr,
        )
        return 2
    except OSError:
        print("The synthetic demo dataset could not be written.", file=sys.stderr)
        return 1

    timestamp_count = math.ceil(options.rows / HOSPITAL_COUNT)
    print(
        f"Generated {options.rows} synthetic demo rows with {len(COLUMNS)} columns "
        f"across {timestamp_count} chronological timestamps."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
