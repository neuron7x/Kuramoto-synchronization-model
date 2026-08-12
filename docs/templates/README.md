---
owner: docs@geosync
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/documentation_governance.md
  - docs/documentation_standardisation_playbook.md
---

# Documentation Template Catalogue

Use this directory to source, version, and review canonical templates for the
GeoSync documentation system. Each template below ships with inline
instructions wrapped in a `<details>` block so authors can remove the guidance
once the document is instantiated. Templates reflect the requirements defined in
the Documentation Governance and Standardisation playbooks.

| Template | Purpose | Primary Audience |
| -------- | ------- | ---------------- |
| `adr.md` | Architecture Decision Records that capture immutable choices. | Architects, Staff Engineers |
| `component_readme.md` | READMEs colocated with code modules describing intent and APIs. | Feature Owners |
| `diagram_sequence.md` | Sequence diagram source and documentation bundle. | Systems Engineers |
| `metrics_table.md` | Normalised schema for quantitative metrics definitions. | SRE, Product Analytics |
| `incident_playbook.md` | Incident response playbooks with verification and recovery steps. | Incident Commanders |
| `release_checklist.md` | Release readiness and change management checklists. | Release Managers |
| `glossary.md` | Controlled vocabulary for domain-specific terms. | Documentation Stewards |
| `onboarding.md` | Role-specific onboarding journeys. | People Operations |
| `run_example.md` | Executable run books for CLI or notebook examples. | Developer Experience |
| `sample_data.md` | Contracts for sample datasets used in docs and tests. | Data Engineering |
| `dataset_card.md` | Dataset cards capturing lineage, quality, and usage notes. | Data Engineering |
| `model_card.md` | Model cards documenting lineage, evaluation, and risks. | MLOps |
| `api_contract.md` | Human-readable API contract aligned with protobuf/OpenAPI specs. | Integrations Team |
| `api_authentication.md` | API authentication, signing, and idempotency guidance. | Platform Engineering |
| `api_error_model.md` | Standard error envelope and retry guidance. | Platform Engineering |
| `api_rate_limits.md` | Rate limit policies, headers, and quotas. | Platform Engineering |
| `api_pagination.md` | Pagination strategies with request/response examples. | Platform Engineering |
| `versioning_policy.md` | Versioning guarantees and branching policy. | Release Managers |
| `compatibility_policy.md` | Backward/forward compatibility guardrails. | Platform Council |
| `example_quickstart.md` | Quickstart walkthrough for first-success flows. | Developer Experience |
| `example_prediction_submission.md` | Idempotent prediction submission walkthrough. | Developer Experience |
| `example_webhook_consumer.md` | Webhook verification and handling example. | Developer Experience |
| `example_sdk_integration.md` | SDK setup and integration example. | Developer Experience |

To introduce a new template, add a file to this directory following the same
pattern: metadata block, guidance `<details>` section, and the copy-paste ready
skeleton. Update this catalogue table and cross-link from the documentation
standardisation playbook.
