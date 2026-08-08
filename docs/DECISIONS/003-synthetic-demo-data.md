# ADR 003: Independent deterministic synthetic demo data

- Status: Accepted
- Date: 2026-08-08

## Context

The application needs a 21-column CSV to start and exercise every view. A separately supplied dataset may have uncertain provenance, redistribution rights, sensitivity, or competition restrictions. Committing or deriving a public demo from such a file would create avoidable data and rights risk.

A useful engineering demo also needs repeatability across clean workspaces and chronological coverage for both model partitions.

## Decision

Provide `scripts/generate_citycare_demo_data.py`, an independently authored generator that does not read, sample, transform, or copy another dataset.

The default generator:

- writes 6,000 synthetic rows to `data/citycare_demo_dataset.csv`;
- creates 30 numbered demonstration hospitals and 200 hourly timestamps;
- uses a deterministic seed of 42;
- fills the exact application schema with bounded formula-derived values;
- includes all declared categorical values and all three capacity labels across chronological partitions;
- accepts only 300-200,000 rows and a bounded 32-bit unsigned seed; and
- refuses to overwrite an existing output unless `--force` is supplied.

The generated CSV is ignored by Git and recreated locally. Source comments and documentation state that it represents no real hospital, patient, incident, or health system and is unsuitable for clinical or operational decisions.

## Consequences

Positive consequences:

- a clean workspace can reproduce the application workflow without a supplied dataset;
- test and demo inputs have explicit formulas and bounds;
- deterministic generation makes engineering regressions easier to compare; and
- supplied material remains outside repository history.

Trade-offs and limits:

- formula-generated relationships can make model metrics look stronger or cleaner than real data;
- synthetic rows do not establish realism, representativeness, fairness, calibration, or clinical validity;
- numbered demonstration hospitals must not be mistaken for real organizations; and
- changing formulas or seeds changes the fitted models and displayed metrics.

## Alternatives considered

### Commit the supplied CSV

Rejected because provenance, sensitivity, and redistribution authorization are not established by the application code.

### Publish a sample derived from the supplied CSV

Rejected because sampling or transformation would still derive from the supplied material and might preserve sensitive or restricted structure.

### Hand-write a tiny fixture as the default demo

Tests use a small purpose-built fixture, but it would not exercise the 30-hospital dashboard and chronological workflow as completely. The deterministic generator provides broader UI coverage while remaining inspectable.
