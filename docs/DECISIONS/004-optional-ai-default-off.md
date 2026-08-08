# ADR 004: Optional AI wording is off by default

- Status: Accepted
- Date: 2026-08-08

## Context

The planner can answer common questions and create a briefing from fixed rules and calculated values. An external language model can improve wording, but using one introduces network availability, data-egress, credential, endpoint, retention, and output-reliability risks.

Operator free text may contain information that the application cannot classify or redact. Prompt instructions cannot provide a confidentiality or factuality guarantee.

## Decision

Keep `AI_ENABLED=false` in the example configuration and make every core workflow usable without an API key or network call.

When explicitly enabled:

- construct a fixed-rule answer or briefing first;
- send only a context block assembled for the requested wording task;
- require HTTPS for non-loopback endpoints and an exact hostname in `AI_ALLOWED_HOSTS`;
- reject URL credentials, query strings, fragments, redirects, and bearer keys over HTTP;
- bound timeout, token, temperature, and response size;
- parse briefing responses into a limited JSON shape; and
- retain fixed-rule content whenever the provider fails or returns unreadable output.

The browser labels whether AI wording was used and keeps the underlying details visible.

## Consequences

Positive consequences:

- local startup and decision-support workflows have no external AI dependency;
- a provider outage does not remove fixed-rule answers;
- endpoint/response controls reduce several credential-forwarding and resource risks; and
- users can see whether wording came from rules or an external model.

Trade-offs and limits:

- assisted wording sends questions and scenario/model context outside the process;
- the application performs no sensitive-data detection or redaction;
- an allowlisted hostname and HTTPS do not establish provider governance, retention, jurisdiction, or correctness;
- a language model can still omit, distort, or overstate supplied context; and
- operators and deployers must make an explicit privacy/security decision before enabling it.

## Alternatives considered

### Require AI for all assistant and briefing features

Rejected because it would make the application dependent on external availability and force data egress for ordinary use.

### Remove AI integration entirely

Not selected because bounded optional wording is useful for controlled evaluation. Continuing to disable it is always supported.

### Enable AI by default with a public provider

Rejected because default egress would be inconsistent with a local, synthetic, inspectable demonstration and could expose unreviewed operator input.
