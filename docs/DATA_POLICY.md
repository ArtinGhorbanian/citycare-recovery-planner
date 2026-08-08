# Data policy

## Repository default

The supported repository demo uses `scripts/generate_citycare_demo_data.py`. Its deterministic scenarios are independently generated for interface and engineering tests. They do not represent real hospitals, patients, incidents, health systems, clinical decisions, or outcomes.

Generated output is ignored by Git and recreated locally. This keeps the repository small and makes the demo provenance explicit.

## Supplied challenge data

`hospital_crisis_realistic_dataset_50000.csv` is also ignored. Its field names and distributions suggest generated operational scenarios, but no authoritative provenance, data card, owner, license, or redistribution permission was found. Do not upload it to GitHub, attach it to a release, include it in screenshots, or provide it to another party until written permission is verified.

## External datasets

Before configuring another CSV, document:

- authoritative source and owner;
- collection or generation method;
- license and redistribution terms;
- permitted purpose and retention requirements;
- whether identifiers or free text can contain personal or confidential data;
- jurisdictional, contractual, clinical, or institutional restrictions; and
- whether model outputs, aggregates, and screenshots can be published.

This prototype does not implement de-identification, consent management, data-subject rights, tenant isolation, row-level authorization, retention automation, or a healthcare compliance program. Do not use protected health information or production operational feeds.

## AI egress

When `AI_ENABLED=true`, structured operational facts and the user's question may be sent to the configured external provider. Do not enter personal, clinical, confidential, or contract-restricted text. Confirm the provider agreement and data-handling settings before enabling egress.
