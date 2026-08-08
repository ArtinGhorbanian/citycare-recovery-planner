# Security Policy

## Supported version

Security fixes are currently considered only for the latest revision on the
private `main` branch and the most recent private preview tag. Earlier commits
and local modifications are not supported.

## Report a vulnerability privately

Do not create an issue, discussion, pull request, or public proof of concept for
a suspected vulnerability.

1. Open the repository's **Security** tab.
2. Choose **Advisories**, then **New draft security advisory**.
3. If private vulnerability reporting or advisories are unavailable, contact a
   repository administrator through the private channel associated with your
   repository access.

Include the affected revision, environment, impact, minimum reproduction steps,
and suggested mitigation if known. Redact credentials, patient information,
private competition content, and unrelated data. Use synthetic inputs wherever
possible. Do not test against systems or data you are not authorized to use.

Maintainers will acknowledge a complete report when practical, assess severity
and scope, and coordinate remediation and disclosure appropriate to the
project's private competition status. No fixed response or resolution time is
promised.

## Current security boundary

The application is a local planning prototype. Its intended baseline is:

- bound to a loopback interface;
- debug mode disabled;
- no authentication or multi-user tenancy;
- AI-provider access optional and disabled by default;
- synthetic or explicitly authorized tabular scenario data; and
- no patient care, diagnosis, treatment, emergency dispatch, or production
  operational use.

Public or shared-network deployment is outside the supported scope. The
prototype does not provide the authentication, authorization, tenant isolation,
abuse controls, durable audit logging, secrets management, availability design,
or rate limiting expected of an internet-facing service. A deployment that
changes this boundary requires a separate threat model and production security
architecture before exposure.

External AI mode sends the user's question and grounded planning context to the
configured provider. Never enable it for protected health information,
credentials, private competition data, or other sensitive material. Provider
terms, retention, residency, and access controls must be reviewed independently.

## In-scope examples

- bypasses of server-side request or numeric-boundary validation;
- unintended disclosure of local configuration, paths, stack traces, or data;
- server-side request forgery or unsafe redirects in optional AI integration;
- cross-site scripting, content-security-policy bypass, or CSV formula
  injection in project-generated exports; and
- dependency vulnerabilities that are reachable in the supported local mode.

Reports about missing internet-scale authentication or rate limiting are not
prototype defects because those capabilities are explicitly out of scope.
Evidence that the application is exposed contrary to its documented boundary,
or that the loopback/debug safeguards can be bypassed, remains relevant.

## Disclosure and changes

Do not publish vulnerability details until maintainers confirm remediation and
coordinate disclosure. Security fixes may change APIs or behavior when needed
to reduce risk. This policy is process guidance, not a warranty or a grant of
rights to access, test, copy, or redistribute the project.
