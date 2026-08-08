# Technical Deep Dive

## Purpose and boundaries

This document explains how the current implementation turns a configured CSV into model outputs and operational decision-support views. It describes code behavior, not medical efficacy. None of the model scores, ranges, heuristics, rankings, or suggested actions have been established here as clinically validated measures.

## Configuration and startup

`app.py` uses a small built-in `.env` reader. An operating-system environment variable takes precedence over a value in `.env`. Relevant settings are shown in `.env.example`:

| Setting | Behavior |
| --- | --- |
| `DATASET_PATH` | Required CSV path, resolved relative to the application directory when not absolute. |
| `HOST` | Bind address; defaults to `127.0.0.1`. |
| `PORT` | Integer from 1 to 65535; invalid values fall back to 5000. |
| `DEBUG` | Enabled only by an explicit true-like value and only on a loopback bind. |
| `AI_ENABLED` | Enables optional external wording; defaults to false. |
| `AI_BASE_URL` | Base URL for an OpenAI-compatible `/chat/completions` endpoint. |
| `AI_ALLOWED_HOSTS` | Comma-separated exact public hostnames permitted for AI egress. |
| `AI_MODEL` | Model identifier passed to the provider. |
| `AI_API_KEY` | Optional bearer credential; never returned to the browser. |
| `AI_TIMEOUT_SECONDS` | Bounded to 1-60 seconds. |
| `AI_MAX_TOKENS` | Bounded to 1-4096 whole tokens. |
| `AI_TEMPERATURE` | Bounded to 0-2. |

Startup is synchronous and trains models before the application reports ready. Failures set `MODEL_READY` to false and expose a generic readiness error while retaining the exception type only in a sanitized console event.

## CSV contract and cleaning

The required 21 columns are defined by `REQUIRED_COLUMNS` in `app.py`.

### Model inputs

- Numeric current-condition fields: incident distance, ambulance arrivals, patient arrival rate, average treatment time, mortality-risk score, bed occupancy, ICU occupancy, equipment usage, nurse-to-patient ratio, and doctors available.
- Categorical fields: hospital identifier, disaster type, triage level, and injury type.
- Derived timestamp fields: year, month, day, hour, and day of week.

### Targets

- `predicted_patients_next_2h`
- `required_icu_beds`
- `required_ventilators`
- `required_staff`
- `overload_risk_score`
- `capacity_flag`

The target names are part of the configured CSV contract. The application does not independently establish how a third-party CSV created those columns. The repository generator creates them from disclosed formulas for demonstration only.

### Cleaning sequence

1. Exact duplicate rows are removed.
2. Timestamps and numeric schema fields are parsed; infinite numeric values become missing.
3. Capacity labels outside `Stable`, `Warning`, and `High Risk` become missing.
4. Rows missing a timestamp, hospital identifier, or target are removed.
5. Hospital identifiers must be positive whole numbers.
6. Missing/blank categories become `Unknown`.
7. Distance, counts, times, ratios, and resource targets are clipped at zero; rate fields are clipped to 0-1.
8. Calendar features are derived and rows are sorted by timestamp.

Unexpected CSV columns are removed after schema validation so they do not remain in the long-lived global data frames. The CSV parser necessarily reads the source file before that projection, so the file path and source itself remain trusted-operator inputs.

## Time-aware split and leakage controls

`split_by_time()` sorts unique timestamps and chooses a boundary after approximately 80% of them. Rows at or before the boundary train the models; later rows form the test set. A timestamp cannot appear in both partitions.

Missing numeric input values are filled with the median calculated from the training partition. Categorical encoding is fitted implicitly by `pandas.get_dummies()` on the training inputs, and test/inference frames are reindexed to the saved training columns. Unknown categories therefore produce zeros for categorical columns that were not observed during training.

The implementation and tests enforce two central leakage controls:

- target columns do not enter `FEATURE_COLUMNS`; and
- training and test timestamps do not overlap.

This design reduces direct target and temporal leakage. It does not prove that the supplied semantics, row-generation process, hospitals, or repeated events are statistically independent.

## Models and evaluation

Two in-memory scikit-learn models are trained with `random_state=42` and `n_jobs=-1`:

| Model | Configuration | Output |
| --- | --- | --- |
| `RandomForestRegressor` | 120 trees, maximum depth 18, minimum leaf size 2 | Five continuous targets in one multi-output fit. |
| `RandomForestClassifier` | 120 trees, maximum depth 18, minimum leaf size 2, `balanced_subsample` class weights | One capacity label. |

The later chronological partition is used to calculate:

- R-squared and mean absolute error for each continuous target;
- classifier accuracy and macro F1;
- confusion matrix and per-class recall, including labels observed in either test data or model classes; and
- the ten largest global feature importances from the regression forest.

Metrics are descriptive for the configured dataset and split. They are not external validation, prospective validation, calibration evidence, or proof of operational benefit.

## Prediction path

`POST /api/predict` accepts a single snapshot. Validation requires a known hospital and known category values, finite non-negative numerics, 0-1 rates, and a timezone-naive timestamp. Values outside observed training ranges are accepted but returned with warnings.

The server then:

1. rebuilds the feature row;
2. runs the regressor and classifier;
3. clips negative operational predictions and bounds overload risk to 0-1;
4. reports the classifier's probability for its selected label as model confidence;
5. rounds people to the nearest whole value and physical resource estimates upward;
6. derives an inter-tree range, resilience index, pressure factors, similar-record summary, strategies, and decision points; and
7. predicts all hospitals' latest records, substituting the current scenario for the selected hospital, to find possible lower-pressure coordination candidates.

### Inter-tree ranges

For each regression target, the implementation takes the 10th and 90th percentiles of the 120 individual tree predictions. These values describe dispersion among trees in this fitted forest. They are not calibrated prediction intervals and should not be read as an 80% probability statement.

### Resilience index

The derived index is:

```text
pressure = 0.35 * predicted overload risk
         + 0.25 * bed occupancy
         + 0.25 * ICU occupancy
         + 0.15 * equipment usage

resilience = 100 * (1 - pressure)
```

The value is clamped to 0-100 and assigned one of three descriptive bands: at least 70, at least 45, or below 45. This is a transparent project heuristic, not a medically validated score.

### Pressure factors

Inputs are compared with training-set medians. Differences greater than 5% are ranked by relative magnitude, with reversed direction for distance, nurse ratio, and doctors available where coded. These are rule-based comparisons, not local model explanations such as SHAP values and not causal effects.

### Similar records

The search first filters to matching disaster type and triage level, relaxes to disaster type if fewer than 20 rows remain, and then relaxes to the complete cleaned dataset if needed. It computes squared standardized distance over ten numeric fields, excludes an exact zero-distance row, and summarizes the nearest 30 records.

The summary describes values present in the configured CSV. It is neither a forecast nor evidence that two situations are clinically equivalent.

## Priority scoring and constrained allocation

Allocation starts with the latest configured record for each hospital. When requested, the current form scenario replaces the selected hospital's latest row.

Four components are calculated:

1. patient safety: mean of min-max-normalized mortality risk, predicted ICU need, and predicted ventilator need;
2. overload relief: mean of predicted overload risk, bed occupancy, ICU occupancy, and equipment usage;
3. patient demand: min-max-normalized predicted patients; and
4. incident proximity: one minus min-max-normalized distance.

Entered non-negative weights are normalized to sum to one. Four zero weights become equal weights. The priority score is 100 times the weighted component sum and is clamped to 0-100.

Each resource type is allocated independently:

1. predicted need is rounded up;
2. weighted need is `rounded need * (1 + priority score / 100)`;
3. each hospital receives the whole part of its proportional reserve share, capped at its predicted need; and
4. remaining units are assigned by largest fractional remainder, then higher priority, until no eligible need or reserve remains.

Tests assert that allocation totals never exceed entered reserves and no hospital receives more than its estimated need. The algorithm does not know existing hospital inventory, physical capacity, transfer feasibility, staffing competencies, travel constraints, or clinical eligibility.

## History analysis

`GET /api/history/<id>` aggregates one hospital's configured records into weekly means and returns the latest 12 weeks. A linear regression over the displayed weekly rate series supplies a direction:

- slope greater than `0.002` per week: worsening;
- slope less than `-0.002` per week: improving; or
- otherwise: stable.

This is a descriptive trend over dataset values. The code intentionally does not extend the validated two-hour target into a long-range forecast.

## Rule-based assistant and optional AI wording

The assistant first constructs an answer from fixed intent rules and current data/model values. It works with `AI_ENABLED=false` and the default demo flow requires no external service.

When AI is enabled:

- chat sends the operator's question, the fixed-rule answer/details, and general dataset/model facts;
- briefing sends the scenario context, prediction values, derived pressure factors, similar-record aggregates, and rule-based actions;
- a system instruction limits the model to the supplied context;
- an unreadable or failed response falls back to fixed-rule content; and
- the interface retains source labels and exact figures.

Prompt instructions are not a confidentiality or factuality guarantee. Input is not scrubbed for personal or health information. See [Optional AI egress](SECURITY_MODEL.md#optional-ai-egress) before enabling it.

## Browser workflow integrity

The browser holds independent request channels for latest-record, history, prediction, briefing, allocation, and chat calls. A new request cancels the prior controller in that channel and increments an identifier. Responses are applied only when their identifier remains current.

Form changes increment a scenario revision. If the revision differs when a prediction returns, the result is visibly stale. Changing the scenario also invalidates an allocation when the allocation includes that scenario. Reserve and weight changes invalidate allocation results directly. CSV export is disabled for a stale allocation.

All server-provided text is assigned with `textContent` or equivalent node construction rather than HTML injection.

## Verification coverage

The repository tests cover:

- deterministic demo-data generation, schema, bounds, categories, chronological coverage, seed behavior, and overwrite refusal;
- happy-path contracts for startup, latest record, history, prediction, allocation, chat, and briefing;
- time-split and feature/target separation;
- resilience and allocation invariants;
- nested JSON types, whole-number identifiers/reserves, finite bounds, timestamps, and request-size rejection;
- security and cache headers plus sanitized startup/error logging;
- environment precedence and conservative bind/debug behavior; and
- AI URL validation, redirect refusal, response-size bounds, numeric configuration bounds, and fallback parsing.

These tests verify the coded contracts. They do not substitute for clinical, operational, privacy, adversarial, performance, or deployment validation.

## Known technical limitations

- Training runs on every process start and can delay readiness.
- Models and metrics are not versioned or persisted as artifacts.
- Global mutable in-memory state assumes one initialized process image; multiple workers would train separate copies.
- The JSON API is not versioned.
- There is no authentication, authorization, tenant isolation, rate limiting, or durable audit trail.
- Public binding exposes every endpoint to any reachable client.
- The built-in Flask server is a development server, not a production serving stack.
- The application has no live capacity, dispatch, EHR, identity, or transfer-system integration.
- The demo generator's structured relationships make it useful for exercising workflows, not for measuring real-world model performance.
