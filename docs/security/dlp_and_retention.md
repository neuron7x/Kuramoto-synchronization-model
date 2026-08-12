---
title: Data Loss Prevention and Retention Policies
description: Classification, retention, deletion automation, leakage detection, and minimisation controls for GeoSync data assets.
---

# Data Loss Prevention and Retention Policies

GeoSync processes market, telemetry, and limited personal data to operate the trading platform. This guide defines how we
classify sensitive information, assign retention periods, automate secure deletion, detect leakage, and minimise personal data
handling to uphold compliance obligations (GDPR, SOC 2, ISO 27001) without constraining engineering velocity.

## Scope and Objectives

- Cover datasets under the control of GeoSync product engineering, observability, support, and operational analytics.
- Align classification and retention rules with the [Governance and Data Controls](../governance.md) guardrails already adopted by the wider organisation.
- Provide actionable runbooks for platform teams to embed DLP protections into services, storage, and CI/CD pipelines.

## Data Classification Framework

GeoSync uses a four-tier classification model. Each tier combines contextual sensitivity with objective detection patterns and control baselines.

| Tier | Label | Typical Examples | Detection Signals | Required Controls |
| --- | --- | --- | --- | --- |
| 4 | **Restricted** | Customer PII (name, contact, payment tokens), production API secrets, private keys | Regexes for personal data, vault secret metadata, key management tags | Strong encryption in transit/at rest, hardware-backed key storage, dual-control access, DLP blocking for egress |
| 3 | **Confidential** | Strategy parameters, proprietary indicators, execution logs with anonymised identifiers | Schema tags, repo path allowlists, column lineage in the data catalog | Encryption in transit/at rest, role-based access (RBAC), field-level masking in analytics, monitored sharing |
| 2 | **Internal** | Aggregated telemetry, anonymised market analytics, internal wiki exports | Data catalog tags, file naming conventions, log aggregation contexts | Authenticated access, watermarking for share-outs, automatic expiry on links |
| 1 | **Public** | Open-source docs, marketing assets, sample datasets | Explicit "public" metadata flag, CDN bucket labels | Integrity controls only, public caching allowed |

**Classification workflow**

1. **Inventory** sources via the central data catalog and infrastructure-as-code manifests (Terraform tags `data_classification`), ensuring every dataset inherits a baseline label.
2. **Detect** sensitive elements at ingestion using the DLP scanner (GitHub action `geosync/dlp-scan@v2`) configured with custom detectors for market account IDs and platform secrets.
3. **Override** classification through schema annotations (`classification="restricted"`) in Pydantic models or database migrations when automated heuristics mislabel data.
4. **Audit** quarterly: security governance reviews `classification_drift` dashboards comparing declared vs detected sensitivity; exceptions require CISO approval.

## Retention Schedule

Retention periods enforce least-privilege temporal access. Timeframes below represent maximum storage duration; shorter windows should be used when product teams can justify them.

| Dataset Category | Sensitivity Tier | System of Record | Maximum Retention | Disposal Method | Notes |
| --- | --- | --- | --- | --- | --- |
| Authentication & audit logs | Restricted | SIEM (Elastic) | 400 days | Vault-managed shredding job with cryptographic erasure | Shorter (180 days) in low-jurisdiction regions when regulatory exemptions apply |
| Trading orders & fills | Confidential | PostgreSQL (production) | 7 years | Partition drop with `pg_purge_partition` workflow | Meets MiFID II retention; legal hold overrides via `legal_hold=true` flag |
| Strategy backtests | Internal | Object storage (`s3://geosync-backtests`) | 365 days | Lifecycle transition to Glacier after 90 days, permanent delete at 365 | Hash-based dedup avoids storing redundant runs |
| Telemetry metrics & traces | Internal | Observability stack (Prometheus, Tempo) | 14 days | Rolling window eviction | Aggregated KPI exports stored separately under 180-day policy |
| Support tickets | Restricted | CRM (Zendesk) | 24 months | Vendor automated deletion | Tickets anonymised after closure; attachments scrubbed via webhook |

Retention logic is codified in the **Data Retention Registry** (`configs/data-retention.yml`), consumed by governance pipelines to provision lifecycle rules and cron jobs.

## Automated Deletion Controls

- **Lifecycle policies** – Object storage buckets define `NoncurrentVersionExpiration` rules matching registry values. Terraform module `modules/data_lifecycle` validates policies during CI.
- **Scheduled jobs** – Kubernetes `CronJob` resources named `retention-*` execute `retention-cleanup` containers that call the Data Retention API (`/internal/retention/expire`). Jobs emit structured logs with dataset IDs and deletion hashes.
- **Cryptographic erasure** – Highly sensitive datasets use envelope encryption. Deletion runs revoke the data key from the KMS CMK and record revocation events in the audit ledger.
- **Verification** – Nightly control reconciliations compare dataset inventories to retention expectations. Failures create PagerDuty incidents tagged `dlp-retention-gap`.

## Leakage Detection and Response

1. **Inline DLP engines** – Email, chat, and code repository integrations block outbound sharing of restricted data. Shared content is fingerprinted to match known data hashes.
2. **Network egress monitoring** – VPC flow logs and proxy records feed anomaly detection models (`analytics/dlp_leak_detector.py`) that flag sudden volume spikes or unapproved destinations.
3. **Endpoint protections** – Managed endpoints enforce clipboard restrictions and prevent removable media writes when restricted data is detected.
4. **Incident handling** – Potential leaks trigger the [Data Incident Runbook](../runbook_data_incident.md). Forensics teams retrieve immutable evidence from the SIEM and S3 object locks.

## Data Minimisation Practices

- **Purpose limitation** – Product teams capture personal data only when mapped to a documented processing activity in the Record of Processing Activities (RoPA).
- **Anonymisation** – Introduce irreversible hashing (`libs/security/hashing.py::hash_identifier`) for identifiers in analytical stores. Salt values rotate quarterly.
- **Pseudonymisation** – Where full removal would break functionality, store references in the `person_tokens` table and segregate token-to-identity mapping inside a restricted schema.
- **On-demand access** – Replace persistent data exports with ephemeral, access-controlled queries delivered through the Insights API with `ttl_seconds` parameters.
- **Secure-by-default defaults** – SDKs and client libraries exclude optional PII fields unless explicitly enabled via configuration flags.

## Compliance Alignment

| Control Objective | Regulation / Framework Mapping | Evidence Source |
| --- | --- | --- |
| Lawful basis, minimisation | GDPR Articles 5 & 6 | RoPA register, consent logs |
| Right to erasure | GDPR Article 17 | Retention API audit ledger, deletion job logs |
| Access controls for sensitive data | ISO 27001 A.8, SOC 2 CC6 | IAM policies, access review certificates |
| Data leakage prevention | ISO 27001 A.8.12, SOC 2 CC7 | DLP incident reports, SIEM dashboards |
| Secure disposal | ISO 27001 A.11.2.7 | Cryptographic erasure evidence, lifecycle policy configs |

## Operational Responsibilities

- **Security Engineering** – Maintain DLP detectors, update retention registry, run quarterly classification audits.
- **SRE** – Operate lifecycle automation jobs, validate monitoring signals, remediate failed deletion runs.
- **Data Platform** – Ensure data catalog metadata stays in sync with schemas, propagate classification tags downstream.
- **Product Owners** – Approve data collection and retention exceptions, coordinate with Legal for holds or regulatory changes.
- **Compliance** – Review evidence packs monthly and handle regulator data requests within SLA.

Embedding these practices across pipelines, storage, and operational workflows ensures GeoSync keeps sensitive data safe, honours retention promises, and remains inspection-ready for regulators and customers alike.
