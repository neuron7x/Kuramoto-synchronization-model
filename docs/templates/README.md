---
owner: docs@tradepulse
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/documentation_governance.md
  - docs/documentation_standardisation_playbook.md
---

# Documentation Template Catalogue

Use this directory to source, version, and review canonical templates for the
TradePulse documentation system. Each template below ships with inline
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
| `api_contract.md` | Human-readable API contract aligned with protobuf/OpenAPI specs. | Integrations Team |
| `versioning_policy.md` | Versioning guarantees and branching policy. | Release Managers |
| `compatibility_policy.md` | Backward/forward compatibility guardrails. | Platform Council |

To introduce a new template, add a file to this directory following the same
pattern: metadata block, guidance `<details>` section, and the copy-paste ready
skeleton. Update this catalogue table and cross-link from the documentation
standardisation playbook.
