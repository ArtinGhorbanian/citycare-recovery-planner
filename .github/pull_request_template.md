## Summary

Describe the user-visible or engineering outcome and link the relevant issue.

Closes #

## Scope

- What changed:
- What intentionally did not change:

## Verification

List the exact commands and manual checks run. At minimum, consider:

- [ ] `python -m pytest`
- [ ] `python -m ruff check app.py scripts tests`
- [ ] `python -m bandit -q -r app.py scripts`
- [ ] `python -m pip check`
- [ ] `node --check static/script.js`
- [ ] Relevant desktop/mobile and keyboard checks for interface changes

## Risk review

- [ ] I did not commit credentials, `.env` files, generated data, logs, or caches.
- [ ] I have authority to contribute this work and disclosed any third-party material and its terms.
- [ ] Test and demonstration data is synthetic or otherwise authorized.
- [ ] I considered security, privacy, accessibility, and failure behavior.
- [ ] External network calls and AI-provider changes are documented and disabled by default where applicable.
- [ ] This change does not imply production, clinical, licensing, ownership, or competition clearance that has not been documented.

## Evidence

Add sanitized logs, screenshots, or before/after notes when they materially help review. Remove secrets, personal data, and restricted competition material first.

## Reviewer notes

Call out migrations, follow-up work, unresolved tradeoffs, or areas that deserve especially careful review.
