# Security Model

## Security posture

The current controls support a local, trusted-operator prototype. They reduce common input, browser, configuration, and optional-AI risks, but they do not create a production security boundary.

The application has no authentication, authorization, tenancy, TLS termination, rate limiting, durable audit logging, or production WSGI configuration. It must not be exposed directly to the public internet.

## Assets

| Asset | Where it exists | Security concern |
| --- | --- | --- |
| Configured CSV | Local file and process memory | May contain operationally sensitive values; provenance and handling requirements depend on the source. |
| Models and metrics | Process memory | Reveal relationships and performance calculated from the configured data. |
| Scenario inputs/results | Browser and transient server request memory | May become sensitive if an operator enters real operational or health-related information. |
| AI API key | Environment or local `.env`; request header when enabled | Credential disclosure or forwarding to an unintended endpoint. |
| Chat questions and briefing context | Browser, Flask process, and optionally external provider | Free text may contain information the application does not detect or remove. |
| Allocation CSV | Browser-generated download | Can be copied or retained outside application controls. |

## Trust boundaries and actors

The intended actor is a trusted local evaluator operating the browser and server on the same machine. Relevant adverse conditions include:

- a network client reaching a non-loopback bind;
- malformed or extreme API input;
- a hostile or misconfigured CSV;
- a malicious or compromised AI endpoint;
- an operator placing confidential content in chat or scenario fields;
- stale or reordered browser responses; and
- browser content injection through server-returned text.

The local filesystem, Python environment, package installation process, host DNS configuration, and explicitly allowlisted AI hostnames remain administrative trust dependencies.

## Implemented controls

### Network and server defaults

- `HOST` defaults to `127.0.0.1`.
- Flask debug mode is off by default.
- A requested debug mode is forcibly disabled on a non-loopback bind.
- The development reloader is disabled, avoiding duplicate model initialization.
- Request bodies are limited to 128 KiB and oversized requests receive a bounded JSON `413` response.

### Input and schema controls

- Every POST route requires a JSON object.
- Nested reserve and weight objects are type-checked.
- Boolean values are not accepted as numbers.
- Numeric inputs must be finite and within broad field-specific bounds.
- Hospital identifiers and reserve units must be whole numbers.
- Rates must be in the 0-1 range; operational values cannot be negative.
- Category values and hospital identifiers must exist in the configured cleaned dataset.
- Timestamps are length-bounded, parseable, and timezone-naive.
- Chat input is text limited to 400 characters.
- The dataset must contain the explicit required schema, and unexpected columns are dropped before long-lived data frames are created.

These checks constrain accidental and direct input abuse. They do not establish that a CSV is trustworthy, non-malicious, legally usable, or free of indirect identifiers.

### Browser controls

Responses include:

- `Content-Security-Policy` restricted to self-hosted scripts, styles, fonts, and connections, with frames and objects disabled;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- a permissions policy disabling camera, microphone, and geolocation; and
- `Strict-Transport-Security` only when Flask sees a secure request.

API responses set `Cache-Control: no-store, max-age=0` and `Pragma: no-cache`.

The browser renders dynamic values with `textContent` and DOM node construction instead of assigning server strings as HTML. Chart.js 4.4.1 is served from the repository rather than fetched at runtime. Request identifiers and cancellation prevent superseded responses from replacing newer workflow state.

### Error and logging controls

- Startup, prediction, allocation, chat, and briefing failures return generic messages rather than exception traces.
- The not-ready status does not return the internal startup exception or dataset path.
- Console events sanitize event names and log an exception type, not its message, request content, key, or endpoint URL.

Logging is deliberately sparse. This reduces accidental disclosure but does not provide incident investigation, accountability, or compliance-grade auditing.

## Optional AI egress

AI assistance is off by default. When `AI_ENABLED=true`, the Flask process makes a server-side request to an OpenAI-compatible `/chat/completions` endpoint.

### Data that can leave the process

For chat, egress can include:

- the operator's free-text question;
- the fixed-rule answer and detail lines;
- configured dataset row counts, period, status counts, and model metrics; and
- facts relevant to the selected hospital or intent.

For briefings, egress can include:

- hospital label/identifier and scenario timestamp;
- disaster, triage, and injury categories;
- entered occupancy, equipment, and other scenario-derived values;
- predicted demand, resources, overload, status, confidence, and resilience;
- pressure-factor text, similar-record aggregates, and rule-based actions.

The application does not detect, redact, pseudonymize, or classify personal data, protected health information, secrets, or confidential operational text. Prompt instructions do not prevent provider retention, misuse, disclosure, or hallucination. Operators must not enable AI or enter sensitive information without an approved provider, contract, retention policy, regional/data-transfer review, and organizational authorization.

### Egress controls

- Non-loopback endpoints must use HTTPS.
- A public endpoint hostname must exactly match `AI_ALLOWED_HOSTS` after normalization.
- URL credentials, query strings, fragments, unsupported schemes, control characters, and malformed ports are rejected.
- Plain HTTP is allowed only for loopback, and a bearer key is rejected for every plain-HTTP URL.
- HTTP redirects are not followed, preventing authorization forwarding to a redirected origin.
- Timeout, token, and temperature settings are bounded.
- Responses are limited to 256 KiB and parsed into expected shapes.
- Any failure retains the fixed-rule answer or briefing.

The URL validator does not perform DNS resolution or pin an endpoint certificate/IP. Administrators control the allowlist and DNS environment. Adding a hostname means trusting its resolution and service behavior.

## Unauthenticated public-bind limitation

`HOST` can be set to `0.0.0.0`, an interface address, or another valid hostname. The only automatic protection added for that choice is disabling Flask debug mode. There is still:

- no login or API credential;
- no role or hospital-level authorization;
- no tenant separation;
- no request-rate or concurrency limit;
- no origin/CSRF token enforcement for compute-triggering POST requests;
- no TLS termination supplied by the application; and
- no restriction on reading status, options, latest records, history, predictions, allocations, or assistant responses.

Anyone who can reach the port can call the APIs and read returned information. Browser same-origin rules are not access control for direct clients. Do not treat a non-loopback bind as a supported deployment.

## Data handling

The repository generator creates deterministic synthetic demo scenarios and writes them to an ignored local path. Those rows do not represent real hospitals or patients. A separately supplied CSV may have different sensitivity and governance; the application cannot infer its provenance.

The server retains cleaned required columns and derived data in global process memory. It does not write source rows, models, requests, or chat to a database. Absence of application persistence does not prevent operating-system paging, terminal capture, browser downloads, reverse-proxy logs, screenshots, backups, or external-provider retention.

## Residual risks

| Risk | Current status | Required direction before shared or production use |
| --- | --- | --- |
| Unauthorized access | No application access control. | Authenticated gateway, role/attribute authorization, least privilege, and tenant boundaries. |
| Transport security | Loopback HTTP default; HSTS only on secure requests. | Managed TLS termination, trusted proxy configuration, and secure headers verified end to end. |
| Denial of service | Body/AI response caps only; model work can be repeatedly triggered. | Rate, concurrency, CPU/memory limits, queueing, timeouts, and operational monitoring. |
| Confidential data entry | No data-loss prevention or redaction. | Data classification, minimization, validation, user policy, provider review, and privacy impact assessment. |
| Auditability | Sanitized console events only. | Structured security/audit logs with access, retention, integrity, and alerting controls. |
| Dependency integrity | Versions are pinned and Chart.js is vendored, but host installation remains trusted. | Automated update review, signed/provenanced builds, artifact scanning, and controlled deployment images. |
| Dataset attacks | Schema and bounds checks exist; source remains trusted. | Provenance validation, quarantined ingestion, size/resource limits, statistical checks, and poisoning review. |
| Model governance | In-process training and descriptive metrics only. | Versioned artifacts, approvals, drift/bias/calibration assessment, rollback, monitoring, and independent validation. |
| Clinical/operational misuse | Interface includes limitations, but outputs may be over-trusted. | Human-factors testing, policy integration, qualified oversight, formal safety case, and applicable regulatory review. |

## Minimum pre-deployment gate

Do not move beyond a local trusted demonstration until all of the following are owned and verified:

1. authorized dataset provenance, classification, retention, and access rules;
2. an explicit deployment threat model and privacy impact assessment;
3. production WSGI service behind an authenticated, rate-limited TLS gateway;
4. authorization tests for every API and hospital/tenant boundary;
5. secrets management outside repository files;
6. structured logging, monitoring, incident response, backup, and recovery;
7. model artifact versioning, independent validation, monitoring, and rollback;
8. external AI provider review or continued AI disablement; and
9. qualified clinical, operational, legal, privacy, and security approvals.

## Verification references

Security-focused contracts are exercised in `tests/test_backend_hardening.py`. Happy-path and self-contained asset behavior are checked in `tests/test_api_contracts.py`. These tests are valuable implementation evidence, not a penetration test or certification.
