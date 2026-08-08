"""Focused tests for the independently generated CityCare demo dataset."""

from __future__ import annotations

import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.generate_citycare_demo_data import (
    CAPACITY_FLAGS,
    COLUMNS,
    DISASTER_TYPES,
    HOSPITAL_COUNT,
    INJURY_TYPES,
    MAX_SEED,
    MIN_ROWS,
    TRIAGE_LEVELS,
    generate_rows,
    main,
)


class CityCareDemoDataTests(unittest.TestCase):
    def test_schema_categories_bounds_and_chronological_coverage(self) -> None:
        rows = list(generate_rows(MIN_ROWS, 12345))

        self.assertEqual(len(rows), MIN_ROWS)
        self.assertEqual(list(rows[0]), COLUMNS)
        self.assertEqual(
            {row["hospital_id"] for row in rows}, set(range(1, HOSPITAL_COUNT + 1))
        )
        self.assertEqual({row["disaster_type"] for row in rows}, set(DISASTER_TYPES))
        self.assertEqual({row["triage_level"] for row in rows}, set(TRIAGE_LEVELS))
        self.assertEqual({row["injury_type"] for row in rows}, set(INJURY_TYPES))
        self.assertEqual({row["capacity_flag"] for row in rows}, set(CAPACITY_FLAGS))

        timestamps = [row["timestamp"] for row in rows]
        unique_timestamps = sorted(set(timestamps))
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertGreaterEqual(len(unique_timestamps), 5)

        cut_index = int(len(unique_timestamps) * 0.8) - 1
        cut_timestamp = unique_timestamps[cut_index]
        train_rows = [row for row in rows if row["timestamp"] <= cut_timestamp]
        test_rows = [row for row in rows if row["timestamp"] > cut_timestamp]
        for partition in (train_rows, test_rows):
            self.assertEqual(
                {row["capacity_flag"] for row in partition}, set(CAPACITY_FLAGS)
            )
            self.assertEqual(
                {row["disaster_type"] for row in partition}, set(DISASTER_TYPES)
            )
            self.assertEqual(
                {row["triage_level"] for row in partition}, set(TRIAGE_LEVELS)
            )
            self.assertEqual(
                {row["injury_type"] for row in partition}, set(INJURY_TYPES)
            )

        integer_fields = (
            "hospital_id",
            "ambulance_arrivals_per_hour",
            "doctor_available",
            "predicted_patients_next_2h",
            "required_icu_beds",
            "required_ventilators",
            "required_staff",
        )
        rate_fields = (
            "mortality_risk_score",
            "bed_occupancy_rate",
            "icu_occupancy_rate",
            "equipment_usage_rate",
            "overload_risk_score",
        )
        for row in rows:
            for field_name in integer_fields:
                self.assertIsInstance(row[field_name], int)
                self.assertGreaterEqual(row[field_name], 0)
            for field_name in rate_fields:
                self.assertGreaterEqual(row[field_name], 0.0)
                self.assertLessEqual(row[field_name], 1.0)
            self.assertGreaterEqual(row["incident_distance_km"], 0.0)
            self.assertLessEqual(
                row["required_ventilators"], row["required_icu_beds"]
            )

    def test_generation_is_reproducible_and_seed_sensitive(self) -> None:
        first = list(generate_rows(MIN_ROWS, 77))
        second = list(generate_rows(MIN_ROWS, 77))
        different_seed = list(generate_rows(MIN_ROWS, 78))

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_seed)

    def test_generation_rejects_unsafe_bounds(self) -> None:
        with self.assertRaises(ValueError):
            list(generate_rows(MIN_ROWS - 1, 0))
        with self.assertRaises(ValueError):
            list(generate_rows(MIN_ROWS, MAX_SEED + 1))

    def test_default_path_parent_creation_and_overwrite_guard(self) -> None:
        original_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            os.chdir(temporary_directory)
            try:
                output = io.StringIO()
                errors = io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    result = main(["--rows", str(MIN_ROWS), "--seed", "9"])
                generated_path = Path("data") / "citycare_demo_dataset.csv"

                self.assertEqual(result, 0)
                self.assertTrue(generated_path.is_file())
                self.assertNotIn(str(Path(temporary_directory)), output.getvalue())
                self.assertEqual(errors.getvalue(), "")

                with generated_path.open(newline="", encoding="utf-8") as data_file:
                    reader = csv.DictReader(data_file)
                    generated_rows = list(reader)
                self.assertEqual(reader.fieldnames, COLUMNS)
                self.assertEqual(len(generated_rows), MIN_ROWS)

                with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                    refused = main(["--rows", str(MIN_ROWS), "--seed", "9"])
                self.assertEqual(refused, 2)
                self.assertNotIn(str(Path(temporary_directory)), errors.getvalue())

                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    replaced = main(
                        ["--rows", str(MIN_ROWS), "--seed", "10", "--force"]
                    )
                self.assertEqual(replaced, 0)
            finally:
                os.chdir(original_directory)


if __name__ == "__main__":
    unittest.main()
