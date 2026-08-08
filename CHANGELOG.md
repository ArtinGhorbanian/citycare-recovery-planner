# Changelog

This file records material project changes. Dates use ISO 8601 format.

## Unreleased

No changes yet.

## 0.1.0-private-preview - 2026-08-08

### Added

- Deterministic, independently created synthetic demonstration-data generator.
- Backend and API regression tests, including hostile input and configuration
  boundary cases.
- Repository governance, issue forms, pull request checklist, dependency update
  configuration, and least-privilege CI.
- Local security guidance and explicit prototype support boundaries.
- Self-hosted Chart.js distribution with its upstream notice.

### Changed

- Reframed the interface as the CityCare Recovery Planner engineering preview.
- Hardened request validation, configuration parsing, optional AI-provider
  access, error handling, response headers, CSV exports, and local server
  defaults.
- Improved responsive navigation, keyboard behavior, focus handling, stale
  result detection, request cancellation, chart fallbacks, and accessible data
  tables.
- Pinned the validated runtime dependency closure and development tools.

### Security

- Added bounded request and external-response sizes, host allowlisting,
  no-redirect AI requests, cache prevention for APIs, and browser security
  headers.
- Removed the supplied competition dataset from version-control scope. Its
  provenance and redistribution rights have not been established.

### Known limitations

- This preview is local-only and is not suitable for clinical, emergency,
  production, or internet-facing use.
- Public release, project licensing, dataset redistribution, and ownership
  claims remain gated on written rights and competition clearance.
