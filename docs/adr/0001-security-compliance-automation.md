# ADR 0001: Security, Compliance, and Documentation Automation

- Status: Accepted
- Date: 2024-05-05
- Decision Makers: Governance Council, Security Engineering, Developer Experience Guild

## Context

GeoSync must satisfy stringent identity and legal obligations covering portfolio-level strategy control, market-data licensing, and dependency governance. Prior documentation lacked prescriptive automation paths for enforcing these controls or documenting architectural decisions.

## Decision

We will institutionalise the following platform capabilities:

1. **Strategy IAM Model** – Define a canonical permission set (`create`, `run`, `kill`, `export`) evaluated per strategy and portfolio. Policies live in Git (`configs/iam/strategies.yaml`) and are enforced at runtime via OPA bundles embedded in orchestration services.
2. **Immutable Governance Trail** – All strategy actions emit structured audit events, while configuration bundles are signed with sigstore metadata. Controllers reject unsigned artifacts and support automated rollback to the most recent trusted version.
3. **Legal Compliance Automation** – Continuous license scanning across Python, Rust, and Go stacks uses curated allow/deny lists. Violations automatically raise remediation pull requests, and waivers expire without renewal.
4. **Market Data Enforcement** – Ingestion and export workflows validate contractual metadata, reject unlicensed feeds, and produce daily attestation reports backed by whitelists and blacklists.
5. **Documentation Discipline** – Core architecture is captured through C4 diagrams, event lifecycle catalogues, and ADRs. MkDocs navigation links these artefacts, and CI enforces freshness via linting commands.

## Consequences

- Engineering teams must maintain policy-as-code repositories and respond to automated remediation PRs.
- CI pipelines gain additional scanning stages, potentially increasing build times, but materially reducing legal exposure.
- Documentation updates become a required deliverable for governance-affecting changes, improving audit readiness.
- Failure to include signed configuration manifests will block deployments, necessitating process adherence from release engineers.

## Alternatives Considered

- **Manual approvals without automation:** Rejected due to audit gaps and high operational toil.
- **Centralised monolithic IAM service:** Rejected in favour of OPA bundles to keep enforcement distributed and resilient to outages.
- **Periodic spreadsheet-based license reviews:** Rejected because it fails to scale with multi-language dependency graphs.
