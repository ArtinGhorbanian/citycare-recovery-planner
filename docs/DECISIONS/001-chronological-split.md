# ADR 001: Chronological split by unique timestamp

- Status: Accepted
- Date: 2026-08-08

## Context

The configured schema contains timestamped hospital scenarios and targets with a two-hour horizon. A random row split could train on later records while evaluating on earlier ones. It could also place rows sharing the same timestamp on both sides, creating an optimistic test context.

Missing-value statistics and categorical feature alignment must also avoid learning from the held-out period.

## Decision

Sort the distinct timestamps and use approximately the earliest 80% for training and the later 20% for testing. Keep all rows with one timestamp on the same side of the boundary.

Calculate numeric imputation medians from training rows only. Build dummy columns from training inputs and reindex test/inference inputs to those saved columns. Exclude all six target columns from the feature frame.

Report regression and classification metrics only for the later held-out partition. Expose the train/test periods and shared-timestamp count in `/api/status`.

## Consequences

Positive consequences:

- evaluation order better matches using past configured records to predict later configured records;
- identical timestamps cannot cross the split boundary;
- held-out rows do not influence numeric imputation or feature-column creation; and
- the split and target exclusion can be asserted directly in tests.

Trade-offs and limits:

- the cut is a single holdout rather than rolling or repeated time-series validation;
- rare categories observed only later are encoded as all-zero categorical indicators;
- temporal separation does not prove event, hospital, or generator independence;
- reported metrics remain specific to the configured dataset; and
- this decision does not provide calibration, external validation, or evidence of medical efficacy.

## Alternatives considered

### Random row split

Rejected because it can mix later and earlier observations and split a shared timestamp across partitions.

### Split by raw row position

Rejected because row order is a weaker contract than parsed timestamps and could divide one timestamp.

### Rolling-origin cross-validation

Not selected for this prototype because it would add startup cost and reporting complexity. It remains a better candidate for a governed evaluation pipeline.
