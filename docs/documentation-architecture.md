# Documentation Architecture Guide

This guide explains how the GeoSync documentation set is organized so that contributors can locate the right place for updates and keep the knowledge base consistent.

## Top-Level Structure

| Directory | Purpose |
|-----------|---------|
| `README.md` | Executive overview for new visitors with installation, highlights, and roadmap links. |
| `docs/` | In-depth product guides grouped by topic. |
| `docs/examples/` | Runnable notebooks and scripts that demonstrate platform capabilities. |
| `DOCUMENTATION_SUMMARY.md` | Change log of major documentation initiatives. |
| `CONTRIBUTING.md` | Contribution standards across code, testing, and documentation. |

## Core Topics Inside `docs/`

GeoSync documentation is segmented by the lifecycle of quantitative research and production trading:

1. **Orientation** – Quick starts and FAQs that help readers gain familiarity fast (`docs/quickstart.md`, `docs/faq.md`).
2. **Implementation** – Extensibility and integration guides that walk through adding indicators, connectors, and APIs (`docs/extending.md`, `docs/integration-api.md`).
3. **Operations** – Monitoring, troubleshooting, and Docker deployment playbooks that support live environments (`docs/monitoring.md`, `docs/troubleshooting.md`, `docs/docker-quickstart.md`).
4. **Scenario Playbooks** – Step-by-step workflows for common contributor tasks (`docs/scenarios.md`).

Each topic area links back to the README and CONTRIBUTING guides so teams can jump between strategic and tactical references without losing context.

## Authoring Principles

To keep the documentation cohesive, apply the following principles whenever you add or edit content:

- **Audience clarity** – Identify whether the page serves researchers, DevOps teams, or compliance stakeholders and write to that skill level.
- **Outcome-first headings** – Every H2 should state the action or decision the reader can make after reading the section.
- **Versioned examples** – Label code blocks with the GeoSync release and dependency versions that were validated.
- **Traceable references** – Cross-link to configuration files, modules, or ADRs using repository-relative paths for long-term durability.
- **Testing completeness** – Whenever you document a workflow, include the commands or scripts used to validate the procedure.

## Contribution Workflow

1. Draft changes in Markdown adhering to the style rules above.
2. Run `make docs-linkcheck` before opening a PR to ensure URLs and internal anchors resolve.
3. Update `DOCUMENTATION_SUMMARY.md` with a short note describing the addition or revision.
4. Add screenshots or terminal output artifacts to `docs/assets/` when visual confirmation adds value.
5. Request review from the Documentation Guild in CODEOWNERS for cross-checking terminology and tone.

Following this structure keeps documentation discoverable and auditable as GeoSync evolves.
