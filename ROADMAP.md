# Roadmap

This roadmap is directional, not a delivery commitment. Work remains subject to
security review, evaluation priorities, contributor capacity, and written
clarification of competition, ownership, licensing, and dataset rights.

## Current: private preview validation

- Complete clean-clone installation and deterministic synthetic-data checks.
- Verify API contracts, hostile-input handling, dependency posture, browser
  accessibility, responsive layouts, exports, and offline chart behavior.
- Keep the supplied competition dataset, local configuration, audit artifacts,
  and credentials outside version control.
- Document known limits, model provenance, allocation behavior, privacy
  boundaries, and reproducible reviewer flows.

## Next: evidence and maintainability

- Expand regression coverage for allocation invariants, degraded states,
  assistive-technology semantics, and export provenance.
- Establish repeatable performance budgets and browser-level accessibility
  checks against synthetic data.
- Add structured architecture decisions for material model, data, dependency,
  and security changes.
- Review dependency updates deliberately and maintain a traceable private
  preview changelog.

## Gated: rights and competition decision

- Obtain written confirmation of source-code ownership and all contributor
  assignments or permissions.
- Obtain explicit dataset provenance, permitted uses, redistribution terms, and
  any attribution requirements.
- Confirm submission visibility, embargo, judging, branding, and
  commercialization restrictions with the competition organizer.
- Select a repository license only after authorized legal review.
- Decide whether any repository, release, dataset, case study, or promotional
  material may become public. Until then, keep them private.

## Future only after authorization and a new threat model

- Design authentication, authorization, tenant isolation, secrets management,
  abuse prevention, rate limiting, audit logging, backup, monitoring, and
  incident-response controls for any shared deployment.
- Conduct privacy, healthcare-regulatory, model-risk, accessibility, and
  operational-safety reviews for the intended jurisdiction and use case.
- Evaluate production data pipelines, model monitoring, human approval,
  rollback, and fail-safe behavior without relying on the prototype's demo
  assumptions.

No roadmap item changes the current rule: the planner is not a medical device,
clinical decision system, emergency dispatch service, or production hospital
operations platform.
