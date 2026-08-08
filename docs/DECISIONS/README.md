# Architecture Decision Records

This directory records consequential technical decisions in the current CityCare Recovery Planner implementation. ADRs describe why a choice was made, what was selected, and which trade-offs remain. They are implementation records, not claims of medical, legal, or production suitability.

## Index

| ADR | Status | Decision |
| --- | --- | --- |
| [001](001-chronological-split.md) | Accepted | Split model evaluation chronologically by unique timestamp. |
| [002](002-local-chartjs.md) | Accepted | Serve Chart.js from a versioned local vendor asset. |
| [003](003-synthetic-demo-data.md) | Accepted | Generate an independent deterministic synthetic demo dataset. |
| [004](004-optional-ai-default-off.md) | Accepted | Keep external AI wording optional, bounded, and off by default. |

## Format

Each ADR includes:

- status and date;
- context;
- decision;
- consequences; and
- alternatives considered.

When a decision changes, add a new ADR that supersedes the old one rather than rewriting history. Small clarifications that do not change the decision may be edited in place.

## Related documents

- [Architecture](../ARCHITECTURE.md)
- [Technical Deep Dive](../TECHNICAL_DEEP_DIVE.md)
- [Security Model](../SECURITY_MODEL.md)
