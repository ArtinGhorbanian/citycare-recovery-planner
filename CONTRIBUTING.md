# Contributing

This repository is maintained as a competition-safe engineering preview. Until
the project's licensing, ownership, dataset, and competition obligations are
resolved in writing, contributions are limited to collaborators who have been
explicitly authorized by the repository maintainers. The absence of a project
license means no general permission to copy, redistribute, or reuse the project
is granted.

## Before starting

1. Search existing issues and pull requests for related work.
2. Open an issue for changes that alter behavior, data use, architecture, or
   external services. A maintainer may waive this for a small, isolated fix.
3. Use only synthetic, public-domain, or otherwise authorized data. Never add
   patient data, credentials, private competition files, or the supplied
   challenge dataset to Git.
4. Keep AI-provider integration optional and disabled by default. Do not send
   sensitive or operational data to an external provider.

## Local setup

Use a dedicated virtual environment with Python 3.14.6. Install the pinned
runtime closure and development tools:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock -r requirements-dev.txt
.venv\Scripts\python scripts\generate_citycare_demo_data.py
Copy-Item .env.example .env
```

On POSIX systems, activate or invoke the environment using the equivalent
`.venv/bin/python` path and copy `.env.example` to `.env`.

The generated CityCare dataset is deterministic and independently created for
demonstration. It does not represent real hospitals, patients, incidents, or
health systems and must not be used for clinical or operational decisions.

## Development expectations

- Create a focused branch from the current `main` branch.
- Prefer small changes with clear failure behavior and tests at the affected
  boundary.
- Preserve loopback-only and debug-off defaults.
- Treat request validation, data minimization, output escaping, and accessible
  keyboard behavior as functional requirements.
- Avoid new external dependencies or network calls unless the issue explains
  the need, risks, maintenance cost, and offline behavior.
- Do not make unsupported claims about model accuracy, safety, ownership,
  endorsement, production readiness, or competition status.

## Required checks

Run the same core checks as CI before requesting review:

```powershell
.venv\Scripts\python -m pip check
.venv\Scripts\python -m ruff check app.py scripts tests
.venv\Scripts\python -m bandit -q -r app.py scripts
node --check static/script.js
.venv\Scripts\python -m pytest
.venv\Scripts\python -m pip_audit -r requirements.lock --no-deps --disable-pip --vulnerability-service osv --timeout 30 --progress-spinner off
```

If Node.js is unavailable and the change cannot affect JavaScript, state that in
the pull request. Dependency auditing requires network access to vulnerability
data; report a service failure separately from a clean audit.

For interface changes, also test keyboard-only operation, visible focus,
reduced-motion behavior, a narrow mobile viewport, and the relevant loading,
empty, stale, and error states. Include sanitized screenshots when they help.

## Pull requests

Complete the pull request template and link the review issue. Keep generated
CSV files, local `.env` files, logs, caches, downloaded artifacts, and supplied
competition material out of the change. A maintainer must review and approve
changes before merge; passing automation is necessary but not sufficient.

Submitting a change does not modify the repository's current rights status or
represent acceptance into any competition submission. Maintainers may defer or
decline a contribution while those obligations remain unresolved. Authorization
to collaborate is not a substitute for contributor-rights documentation;
maintainers may require written confirmation of authorship, authority, and any
third-party terms before merge.

## Security and conduct

Do not open a public issue for a suspected vulnerability. Follow
[SECURITY.md](SECURITY.md). Participation is also subject to
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
