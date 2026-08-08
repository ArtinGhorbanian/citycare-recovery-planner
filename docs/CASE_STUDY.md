# Engineering Case Study

## Summary

CityCare Recovery Planner was refactored from a large local Flask dashboard into a more reproducible and reviewable decision-support prototype. The work concentrated on preserving its two-hour prediction and constrained-allocation concepts while making assumptions, data boundaries, failure modes, and workflow state visible.

This is an engineering case study, not evidence of medical efficacy, production readiness, or performance on real hospitals. The default demonstration data is independently generated and synthetic.

## Initial engineering problem

The prototype already combined dataset exploration, random-forest predictions, allocation logic, weekly trends, strategies, and an assistant in one application. That breadth created several review challenges:

- the runtime depended on local configuration and a CSV but lacked a reproducible demonstration-data path;
- target leakage and time-split assumptions needed explicit contracts;
- API validation, error disclosure, network defaults, and optional AI egress needed defensive boundaries;
- asynchronous browser requests could outlive the scenario that initiated them;
- prediction and allocation results needed a visible current/stale lifecycle;
- a runtime CDN dependency could fail or change independently of the repository; and
- technical limitations needed to be documented alongside the implementation.

The goal was not to replace the domain concept or claim a new validated capability. It was to make the existing prototype safer to inspect, deterministic to demonstrate, and easier to challenge.

## Constraints

- Preserve the documented 21-column application schema and core two-hour workflow.
- Do not invent long-range forecasts or physical capacity data the schema does not contain.
- Keep the application usable with optional AI disabled.
- Avoid treating model confidence, inter-tree dispersion, resilience, priority, or similar-record results as clinical measures.
- Keep supplied data separate from repository-generated demo artifacts.
- Make local use the default; do not imply that a configurable network bind is a supported public deployment.

## Engineering changes

### Reproducible data path

`scripts/generate_citycare_demo_data.py` now creates 6,000 deterministic synthetic rows by default across 30 numbered demonstration hospitals. The generator uses only formulas declared in that file, accepts bounded row/seed parameters, and refuses to overwrite an existing file without `--force`.

The generated CSV is ignored by Git and can be recreated locally. Generator tests verify its schema, categories, numeric bounds, chronological coverage, deterministic seed behavior, and overwrite guard.

### Time-aware model pipeline

The startup pipeline explicitly projects to the required schema, cleans invalid targets and identifiers, and creates a chronological split over unique timestamps. Training-only medians fill missing numeric inputs. Feature construction excludes every output column, and tests assert both target separation and zero timestamp overlap.

Held-out metrics are reported without replacing poor values. The interface distinguishes model outputs from project heuristics and warns when a scenario lies outside the observed training range.

### Defensive API and runtime behavior

POST bodies are object-checked and capped at 128 KiB. Numeric, categorical, identifier, timestamp, reserve, and weight fields have explicit type/range checks. Failures return bounded JSON and sanitized messages; internal console events omit exception messages, secrets, URLs, and request content.

The server defaults to loopback and debug off. Debug is refused for non-loopback binds. Browser responses add a self-only content security policy and other defensive headers, while API responses are marked `no-store`.

These controls improve the local prototype but do not add authentication, production serving, or a public deployment boundary.

### Bounded optional AI integration

Rule-based answers and briefings remain the baseline. When explicitly enabled, AI calls require an exact allowlisted hostname for public endpoints, HTTPS outside loopback, bounded configuration, no redirects, and a 256 KiB response limit. Unreadable or failed responses fall back to fixed-rule content.

The interface reports whether AI wording was used. Documentation states exactly which free text and scenario/model context may leave the process. There is no automatic sensitive-data redaction, so AI remains disabled in the default demo.

### Workflow integrity and accessibility

The browser now tracks pending requests by channel, aborts superseded work where supported, and ignores responses whose request identifier is no longer current. Scenario revisions mark predictions stale; scenario/reserve/weight changes mark allocations stale; stale CSV downloads are disabled.

Navigation exposes locked, ready, and stale states. Hash-based views move keyboard focus, mobile navigation traps focus and restores it on close, errors associate with fields, live regions announce state, and chart values remain accessible in tables.

### Self-contained visualization

Chart.js 4.4.1 and its MIT license text are stored under `static/vendor/`. The content security policy can therefore keep `script-src` and `connect-src` limited to the application origin. If chart initialization fails, data tables remain available.

## Evidence produced

| Concern | Repository evidence |
| --- | --- |
| Generator behavior | `tests/test_generate_citycare_demo_data.py` |
| Browser/API happy paths | `tests/test_api_contracts.py` |
| Leakage and allocation invariants | `tests/test_backend_hardening.py` |
| Input and request bounds | Backend hardening tests for object types, finite values, timestamps, whole units, and body limits |
| Header/error behavior | Backend tests for security headers, no-store responses, sanitized readiness, and sanitized logging |
| AI boundary | Backend tests for URL validation, redirect refusal, size limits, bounded settings, and fallback parsing |
| Source/data defaults | `.env.example`, `.gitignore`, and the synthetic generator |
| Dependency reproducibility | `requirements.txt`, `requirements.lock`, and the self-hosted Chart.js bundle/license |

Automated tests verify these coded contracts. They do not cover clinical validity, real-world transport/capacity workflows, privacy compliance, adversarial penetration, load behavior, or production operations.

## Resulting system qualities

- A reviewer can create a known demo dataset without access to a separately supplied CSV.
- The model split, features, targets, metrics, heuristics, and allocation method are inspectable in code and documentation.
- The application remains functional without an AI provider.
- Browser state identifies stale results instead of silently presenting them as current.
- Common malformed-input and optional-egress cases fail with bounded behavior.
- The browser runtime no longer requires a third-party chart CDN.

These are maintainability, transparency, and defensive-engineering improvements. They do not establish that any recommendation is safe for real operations.

## Remaining work before any real deployment

The largest remaining gaps are intentionally not hidden by this case study:

- authorized, governed, representative data and independent outcome validation;
- model calibration, bias, drift, robustness, versioning, approval, and rollback;
- authenticated/authorized APIs and tenant boundaries;
- production WSGI, TLS gateway, rate limits, resource isolation, monitoring, and audit logs;
- integration with verified inventory, transport, transfer, and incident-command systems;
- privacy controls and a decision on whether external AI egress is permitted at all;
- formal human-factors, safety, clinical, operational, legal, and regulatory review; and
- tested continuity, incident response, backup, recovery, and change management.

Until those gaps are addressed, the appropriate use is local engineering evaluation with synthetic data and qualified interpretation.
