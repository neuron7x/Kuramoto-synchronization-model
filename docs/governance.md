# Governance and Data Controls

This guide defines the governance guardrails for TradePulse across access management, data contracts, privacy, and cataloguing. Policies apply to all production and pre-production environments unless explicitly waived by the Governance Council. Dataset-level provenance and validation rules are captured in [DATA_GOVERNANCE.md](DATA_GOVERNANCE.md) and must be followed for any calibration or certification workflow that consumes repository data.

## Role-Based Access Control (RBAC)

| Role | Scope | Permitted Actions | Enforced Through |
| ---- | ----- | ----------------- | ---------------- |
| **Ingestion Operator** | Streaming and batch ingestion services | Manage connectors, configure schemas, run validation pipelines, rotate ingestion secrets. No direct database writes outside staging schemas. | IAM policies on `ingestion-*` services, service mesh policy allowing `POST/PUT` to ingestion APIs, GitOps repository permissions for connector configs. |
| **Backtest Engineer** | Research compute clusters and artifact stores | Launch backtest jobs, read historical market data, publish backtest reports, submit feature proposals. No production execution permissions. | RBAC in workflow orchestrator (e.g., Argo), read-only S3 bucket policies, GitHub team `backtest-dev`. |
| **Execution Trader** | Live execution and risk control services | Approve deployment of execution models, adjust risk limits, halt strategies, monitor execution telemetry. Cannot modify ingestion connectors or raw data. | Fine-grained roles in execution control plane, feature-flag management, emergency break-glass tokens logged in PAM. |
| **UI Analyst** | Web UI and analytics workspaces | View aggregated dashboards, download approved reports, annotate anomalies. No direct access to raw feature stores or execution toggles. | OIDC group `ui-analyst`, reverse-proxy ACLs, row/column level security on BI datasets. |

### Strategy and Portfolio Permissions

- **Action matrix** – Expose four canonical permissions per strategy or portfolio: `create`, `run`, `kill`, and `export`. Policies are codified in `configs/iam/strategies.yaml` with explicit role → strategy mappings and TTLs for temporary access.
- **Hierarchical evaluation** – Portfolio-level grants inherit to contained strategies, while strategy overrides can further restrict actions (e.g., allow `run` but deny `export`). Evaluation uses OPA/Rego bundles shipped with deployment artifacts.
- **Contextual constraints** – Runtime guards require the calling identity, declared change ticket, and deployment hash to match the signed approval manifest before executing `create` or `run` workflows. Requests failing validation are rejected with auditable error codes.
- **Self-service workflow** – Access requests leverage ServiceNow-style forms that trigger Terraform Cloud runs updating the IAM config repository. All merges require multi-party approval (requester manager + system owner).

### Access Logging and Configuration Integrity

1. **Action audit trail** – Every invocation of `create`, `run`, `kill`, or `export` emits a structured log (JSON) to the governance topic with identity, strategy ID, parameter diff, approval reference, and cryptographic digest of the before/after configuration. Logs replicate to long-term storage with 400-day retention and are cross-checked nightly against the compliance ledger.
2. **Configuration signing** – Strategy manifests, risk limits, and pipeline configs are stored in Git. A sigstore-based signing step runs in CI, attaching provenance metadata (commit SHA, signer identity) before release bundles are published. Parameter changes require dual signatures (requester + approver) which are validated before promotion.
3. **Version rollback** – The deployment controller verifies signatures before promoting configs. If validation fails or a regression is detected, operators can request an automated rollback to the previous signed version, tracked through change tickets. Rollbacks emit an `audit.rollback` event referencing the triggering incident ID.
4. **Immutable audit snapshots** – Each approved change generates an append-only record in the compliance ledger (PostgreSQL + pgcrypto) linking Git commit, signer, and deployment environment for evidentiary purposes. Snapshots are sealed with a Merkle root so tampering invalidates the entire chain.
5. **Critical action 2FA** – Strategy activation, kill-switch, and risk limit overrides enforce second-factor confirmation (FIDO2 or TOTP). The audit event stores the authenticator type and challenge nonce, blocking execution if the proof is absent.

### Temporary Debug Access Tokens

- **Scoped issuance** – Engineers can mint temporary debug tokens with `tradepulse-cli auth mint --scope debug --ttl 2h`. Tokens are namespaced per environment and include explicit expiry metadata.
- **Automatic expiration** – Tokens are backed by the identity provider with short-lived credentials (≤4 hours). Revocation occurs automatically at expiry or on manual kill via `tradepulse-cli auth revoke --token <id>`.
- **Usage journal** – Every token use emits `auth.token_usage` events recording subject, IP, scope, and command executed. The journal feeds into weekly access review dashboards.
- **Approval workflow** – Minting tokens requires peer approval captured through the governance service. The approval ID is embedded in the token claims and validated by gateways before honoring the request.

### Strategy Change Sign-Off Workflow

1. Engineer submits parameter update through the governance UI, attaching justification and expected impact.
2. Change is serialized as a signed bundle (YAML + diff digest) and routed for dual approval (strategy owner + risk officer).
3. Upon approval, CI stamps the bundle with sigstore metadata and publishes to the artifact registry.
4. Deployment controllers validate signatures, enforce 2FA confirmation, and emit `strategy.change.applied` events with the diff hash and signers.
5. Audit dashboards reconcile applied changes against approval manifests nightly; mismatches trigger incident escalation.

### Service-Level Access Policies

1. **Zero trust mesh** – mTLS enforced between services with SPIFFE identities, limiting service-to-service calls to declared intents (e.g., ingestion services cannot call execution write endpoints). Operational procedures live in the [Zero Trust Service Mesh Runbook](security/zero_trust_runbook.md).
2. **Environment segregation** – staging and production namespaces enforce namespace-level network policies; execution services only accept traffic from approved front doors.
3. **Secrets governance** – HashiCorp Vault policies scoped per role; dynamic secrets for databases expire within 1 hour; audited secret rotation via CI workflows.
4. **Least privilege automation** – Terraform modules expose role bindings as code with review requirements and automated drift detection (weekly `terraform plan` reports).

## Data Contracts

### Contract Types

| Data Tier | Owner | Schema & Quality Guarantees | Distribution | Consumers |
| --------- | ----- | -------------------------- | ------------ | --------- |
| **Raw** | Data Engineering | Immutable schema with additive fields, partitioned by ingest timestamp, mandatory lineage tags. Quality checks: format validation, checksum verification, source completeness threshold ≥95%. | Object storage (`raw/` prefix), replayable change data capture streams. | Feature pipelines, archive services. |
| **Aggregated** | Analytics Engineering | Derived tables with documented grain, aggregation windows, and null-handling rules. Quality checks: aggregation parity tests, anomaly detection (<3σ). | Warehouse schemas (`analytics.`), curated API endpoints. | UI dashboards, risk analytics, reporting. |
| **Feature** | ML Engineering | Feature store entities with versioned feature views, point-in-time correctness, and training-serving skew monitors. Quality checks: feature drift alerts, data freshness SLA <15 minutes. | Feature store registry, batch exports for model training. | Backtest platform, execution scoring services. |

### Change Management

- **Non-breaking changes** – additive columns, extended enumerations with defaults, new optional attributes. Require:
  - 3-day notice via `#data-contracts` channel.
  - Updated contract YAML in `data/contracts/` with semantic version patch increment.
  - Automated schema compatibility tests passing in CI.
- **Breaking changes** – column removal/rename, data type narrowing, primary key changes, SLA relaxations. Require:
  - 14-day RFC with impact analysis and rollback plan.
  - Approval from Data Governance Council and affected service owners.
  - Coordinated release window with feature flag or dual-write strategy.
  - Major version bump and migration playbook stored in `docs/migrations/`.

## Privacy and PII Handling

1. **Collection Policy** – Collect only fields required for trading compliance, regulatory reporting, or customer deliverables. All PII attributes must be catalogued with data owner sign-off and tagged in the metadata store.
2. **Masking & Tokenisation** – Apply irreversible hashing for persistent storage of identifiers; use format-preserving tokenisation for operational workflows. Access to de-tokenisation services requires break-glass approval with session recording.
3. **Retention & Deletion** – Raw PII limited to 90 days unless regulatory retention requires longer. Aggregated datasets must strip direct identifiers. Quarterly retention audits verify deletion jobs succeeded.
4. **CI/CD Enforcement** –
   - Static checks ensuring migrations referencing PII tables include masking functions.
   - Unit tests verifying PII columns are excluded from public exports.
   - Automated policy-as-code (OPA/Rego) gate in CI to block deployments if datasets lack privacy tags or retention rules.

## Legal and License Compliance

- **Dependency bill of materials (SBOM)** – All Python, Rust, and Go builds emit SPDX-compatible SBOMs stored under `reports/sbom/`. SBOMs feed into the weekly license review job.
- **License scanning pipeline** – CI runs `pip-licenses`, `cargo-deny`, and `go-licenses` with curated allow/deny lists defined in `conf/license_policies.yaml`. Builds fail if a dependency violates the whitelist or appears on the blacklist.
- **Automated remediation PRs** – A scheduled GitHub Action opens pull requests applying the recommended upgrade or replacement for flagged dependencies, tagging the Security and Legal teams for review.
- **Exception workflow** – Temporary exceptions require a signed waiver uploaded to `reports/legal/waivers/` and expire automatically after 30 days unless renewed.

## Market Data Usage Governance

1. **Source verification** – Data ingestion pipelines validate that feed metadata includes contractual identifiers (EULA ID, region, redistribution flag). Jobs without compliant metadata halt ingestion and alert the legal compliance channel.
2. **Usage policy enforcement** – Export jobs evaluate data lineage. If an output includes sources tagged `redistribution-restricted`, only aggregated or delayed views are allowed. Attempted violations trigger automatic job cancellation.
3. **Automated certification checks** – Daily compliance runs compare active sources against vendor whitelists/blacklists maintained in `data/market_data_sources.yaml`, producing signed attestations stored in `reports/legal/vendor_attestations/`.
4. **Incident response** – Suspected misuse spawns a governance incident with forensic log preservation, root-cause template, and vendor notification workflow within 24 hours.

## Documentation and Developer Experience Guardrails

- **C4 model coverage** – Architectural documentation must provide system, container, and component-level C4 diagrams (`docs/assets/c4/`). Diagrams are versioned alongside the codebase and regenerated via `make docs-c4` before merge.
- **Event lifecycle catalogues** – Each major workflow (ingestion, strategy deployment, execution) maintains an event sequence table detailing producers, consumers, schemas, and SLA expectations. Tables live in `docs/events/` and are linted for completeness during CI.
- **Architecture Decision Records (ADR)** – Significant governance or platform decisions require ADRs stored in `docs/adr/` using the standard template. ADRs are referenced from affected documentation to keep context discoverable.
- **Developer enablement** – MkDocs navigation exposes governance resources, and internal training includes quarterly refreshers with sandbox exercises reviewing access requests, legal scans, and documentation updates.

## Data Catalog, Lineage, and Source Inventory

- **Central Metadata Store** – Use an OpenMetadata deployment storing dataset schemas, owners, SLAs, and privacy classifications. Each dataset entry includes contact information and runbooks.
- **Lineage Tracking** – Instrument ingestion and transformation jobs to emit OpenLineage events. Visual lineage graphs connect raw sources → aggregated tables → feature views → downstream services.
- **Versioning** – Datasets carry semantic versions aligned with data contract versions. Historical snapshots are persisted to enable point-in-time recovery and auditability.
- **Source Inventory** – Maintain an authoritative inventory (`data/sources.yaml`) listing external vendors, regulatory feeds, internal microservices, refresh cadence, and contractual obligations. Inventory updates trigger governance review through the change management workflow.
- **Access Transparency** – Usage analytics dashboards monitor dataset reads by role, surfacing anomalous access patterns for investigation.

## Operational Cadence

- Monthly governance review to assess RBAC exceptions, contract changes, and privacy incidents.
- Quarterly penetration test focused on data exfiltration paths and identity boundary hardening.
- Annual recertification of all data sources, with lineage validation and contract renewal.
