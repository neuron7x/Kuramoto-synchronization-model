# Disaster Recovery & Multi-Region Failover Runbook

## Purpose

This runbook codifies the recovery plan for catastrophic failures that threaten
TradePulse production availability or data integrity. It aligns teams on
recovery point objectives (RPO), recovery time objectives (RTO), and the
operational playbooks required to restore trading safely across geographic
regions with zero tolerance for uncontrolled data loss.

## Scope

- **Environments** – Production and warm-standby regions (Americas, EMEA, APAC).
- **Systems** – Strategy runtime, order execution, market data ingestion,
  analytics API, feature stores, compliance audit trail, CI/CD delivery
  pipeline.
- **Data Stores** – PostgreSQL (transactional state), Kafka (event bus), Redis
  (online feature cache), Iceberg/Delta (historical lake), object storage
  (artifacts and backups).
- **Stakeholders** – SRE (incident commander), Infrastructure (database and
  network), Data Platform (lake), Execution Platform (order routing), Compliance
  (regulatory evidence), Security (key management).

## Recovery Objectives

| Capability | Target RPO | Target RTO | Notes |
| ---------- | --------- | --------- | ----- |
| PostgreSQL transactional data | ≤ 60 seconds | ≤ 10 minutes | Synchronous replication within metro, async multi-region with WAL shipping. |
| Kafka critical topics (`orders`, `fills`, `risk_events`) | ≤ 30 seconds | ≤ 8 minutes | MirrorMaker 2 geo-replication with offset translation; enforce min ISR ≥ 3. |
| Redis online feature cache | ≤ 5 minutes (replayable) | ≤ 5 minutes | Treated as cache; rebuild via feature snapshot replay. |
| Object storage artifacts (models, configs) | ≤ 5 minutes | ≤ 20 minutes | Versioned bucket with cross-region replication (CRR) and immutable retention. |
| Iceberg/Delta analytical lake | ≤ 15 minutes | ≤ 45 minutes | Incremental metadata snapshots + S3/Blob storage replication. |
| CI/CD & secrets | ≤ 5 minutes | ≤ 15 minutes | Git mirror + HashiCorp Vault DR secondaries with auto-unseal. |

### RPO/RTO Governance

- **Measurement** – Real-time replication lag dashboards expose `rpo_lag_seconds` and `rto_simulated_minutes` Prometheus metrics. Alert at 50% of the SLA to allow proactive mitigation. Each restore or failover captures achieved RPO/RTO in the resilience evidence log curated by the SRE team.
- **Drift Detection** – Alertmanager rules in `observability/alerts.json` raise SEV-1 pages when replication lag or failover simulations exceed thresholds for two consecutive evaluation periods.
- **Change Management** – Any schema or topology change requires updating the RPO/RTO table through a pull request reviewed by SRE + Data Platform. Releases referencing stale objectives are blocked during change-advisory review.

### Scenario Catalogue

| Scenario | Trigger | Expected RPO/RTO | Response Summary |
| --- | --- | --- | --- |
| Region-wide outage | Loss of primary cloud region, network partition | RPO ≤ 60 s, RTO ≤ 15 min | Execute full failover workflow, promote secondary databases, shift mesh routing, activate client comms template A. |
| Logical data corruption | Bad deploy or operator error mutates ledger | RPO ≤ 60 s, RTO ≤ 30 min | Freeze writes, perform point-in-time recovery (PITR) from immutable backups, replay Kafka offsets post-restore. |
| Security event | Compromised credentials, forced rotation | RPO ≤ 5 min, RTO ≤ 20 min | Rotate Vault primaries, re-issue service identities, audit access logs, coordinate with security comms template C. |
| Upstream dependency loss | Market data vendor outage | RPO ≤ 5 min, RTO ≤ 5 min | Switch to secondary providers, enable synthetic heartbeat generator, ensure replay once vendor recovers. |
| Storage durability alert | Object store replication lag > SLA | RPO ≤ 15 min, RTO ≤ 30 min | Pause non-essential writes, trigger accelerated replication job, validate checksum parity before unfreezing. |

Breaching an objective requires immediate SEV-1 declaration, regulator-ready
communication, and postmortem with remediation in the next release window.

## Architecture & Topology

1. **Active/Active edge, Active/Passive core** – API edge and WebSockets run in
   active/active mode across primary and secondary regions using GSLB with
   latency-based routing and health checks. Stateful services (PostgreSQL,
   Kafka) operate in active/passive with automated promotion.
2. **Deterministic infrastructure-as-code** – Terraform modules under
   `infra/terraform/` manage VPC, subnets, security groups, load balancers, and
   cluster nodes. Disaster recovery reuses the same definitions to guarantee
   parity, with deployment overlays sourced from `deploy/`.
3. **Dedicated replication links** – Inter-region replication occurs over
   private connectivity (MPLS or provider backbone) with QoS prioritising WAL
   and Kafka traffic. TLS 1.3 mutual auth and hardware-backed keys protect data
   in transit.
4. **Configuration and secret management** – Vault enterprise clusters operate
   in performance + DR mode. `vault operator dr failover` is pre-authorised for
   SRE with quorum-backed recovery keys. Application configs (Helm charts, kpt)
   reference Vault/Secrets Manager to avoid stale inline secrets.

## Backup & Snapshot Strategy

| Component | Mechanism | Frequency | Retention | Validation |
| --------- | -------- | --------- | --------- | ---------- |
| PostgreSQL | Native streaming replication + `pg_basebackup` PITR snapshots to versioned object storage | Continuous + hourly base backups | 35 days online, quarterly archive to glacier tier | Daily checksum verification, weekly restore rehearsal. |
| Kafka | Tiered storage (remote log) + MirrorMaker 2 cross-region replication | Continuous | 14 days remote log, 7 days MirrorMaker lag tolerance | Daily consumer offset parity check, weekly replay drill. |
| Redis | `redis-cli --rdb` snapshot to encrypted bucket + AOF shipping | Hourly | 7 days | Automated restore into canary cluster nightly. |
| Iceberg/Delta | Metadata snapshots + storage provider versioning | Every commit | 90 days | Automated schema checksum, monthly time-travel restore. |
| Vault & Secrets | Integrated storage snapshots + DR secondary | 15 minutes | 30 days | Quarterly failover exercise validated via seal/unseal logs. |
| CI/CD Artifacts | Signed Git mirrors + OCI registry replication | Push triggered | 30 days + immutable tags | Post-push diff check, monthly signature audit. |

Backups are encrypted using AES-256-GCM envelopes with keys in HSM-backed KMS.
Signature verification (Sigstore/Rekor) is enforced before restores.

### Backup Compliance Checklist

1. Backup jobs emit structured logs with UUIDs that map to the retention catalogue maintained in the resilience evidence log.
2. Daily automation validates bucket immutability and rotation of encryption keys; results flow into the observability dashboards under the `Backup Health` panel.
3. Quarterly manual audit confirms restoration of randomly sampled backups into isolated sandboxes, comparing row counts and SHA-256 dataset hashes against production snapshots.
4. Any failed validation auto-opens a `BCP-BLOCKER` Jira issue with assigned owner and due date within 5 business days.

## Recovery Testing Program

1. **Quarterly game-day** – Simulate total region loss; execute full failover and
   rollback following this runbook. Capture metrics for RTO adherence.
2. **Monthly targeted restore** – Rotate between PostgreSQL, Kafka, and object
   storage restores in staging. Validate parity against production checksums.
3. **Weekly tabletop** – Review dependency graph, update contact roster, confirm
   access tokens, and run through decision trees.
4. **Automated drift detection** – CI runs `terraform plan` against each region
   using the modules in `infra/terraform/`. Any unexpected diff blocks releases
   until remediated and signed off by SRE.

### Automated Recovery Tests

- **Disaster Replay CI** – The nightly `disaster-replay` GitHub Actions workflow provisions ephemeral clusters, restores the latest backups, replays last-hour Kafka topics, and runs deterministic health assertions. Failures block merges tagged `release/*`.
- **RTO Smoke Jobs** – Synthetic workloads (`python scripts/smoke_e2e.py --dr-mode`) execute every 4 hours in the warm standby region to ensure cold paths stay hot. Results push to the Prometheus `dr_smoke_success` gauge exposed via the observability exporters.
- **Chaos Sequencing** – Integrated with the chaos testing program (`docs/resilience.md`), at least one scenario each month must cover cross-region failover to validate replication, DNS cutovers, and automation scripts.
- **Audit Evidence** – Test artifacts (logs, Grafana snapshots, restore manifests) are archived alongside the run results in the resilience evidence repository for regulator-ready evidence.

Evidence for each exercise is archived in `reports/disaster-recovery/` with
Grafana exports, audit logs, and sign-off from domain leads.

## Failover Procedure (Primary → Secondary Region)

1. **Declare Incident (SEV-1)**
   - Incident commander opens `#inc-dr-<date>` channel and PagerDuty bridge.
   - Freeze deployments (`argo rollouts pause --all`).
   - Notify compliance and customer success via pre-approved templates.
2. **Stabilise Data Streams**
   - Halt new strategy activations (`POST /admin/strategies/disable-new`).
   - Quiesce order gateway (`execution-service` toggles `ACCEPT_NEW_ORDERS=false`).
   - Confirm Kafka replication lag < 30 s; if exceeded, snapshot offsets.
3. **Promote Secondary Data Stores**
   - PostgreSQL: `patronictl failover --force --candidate <secondary-primary>`.
     Validate WAL replay complete (`pg_stat_wal_receiver` idle).
   - Kafka: Promote the MirrorMaker target cluster and update client bootstrap
     DNS records or service mesh endpoints via the Terraform/Helm overrides for
     the secondary region. Ensure ISR rebuilt before resuming writes.
   - Redis: Switch HAProxy/Envoy upstream to the standby cluster. Hydrate hot
     keys by replaying the latest feature snapshot using
     `python scripts/resilient_data_sync.py` with the DR transfer manifest.
4. **Repoint Application Control Plane**
   - Update service mesh global config (`istioctl x remote-discovery`) to prefer
     secondary region endpoints.
   - Apply Helm/ArgoCD overrides (`region=secondary`, `primary=false`).
   - Redeploy execution + API workloads in secondary region with `kubectl
     rollout restart`.
5. **Verify Health**
   - Run the deterministic smoke harness (`python scripts/smoke_e2e.py`) against
     the DR validation dataset (default `data/sample.csv` or region-specific
     snapshot) to confirm ingestion → signal → order flow.
   - Confirm SLO dashboards within tolerance (latency p95, order ack ratio) via
     the Grafana exports in `observability/dashboards/tradepulse-overview.json`.
   - Ensure audit trail ingestion resumed by inspecting Kafka consumer lag
     panels and PostgreSQL replication status views.
6. **Resume Trading**
   - Lift order gateway freeze under incident commander approval.
   - Notify clients with recovery confirmation and updated region information.
   - Continue heightened monitoring for 2 hours.

## Data Loss Mitigation & Validation

- **Ledger reconciliation** – Execute SQL parity checks against the canonical
  tables defined in `schemas/postgres/0001_trading_core.sql`, comparing
  aggregates (counts, sums, balances) between the last healthy snapshot and the
  restored cluster. Any discrepancy is SEV-1 and requires manual broker
  reconciliation before trading resumes.
- **Feature consistency** – Use the `FeatureParityCoordinator` in
  `core/data/parity.py` to compare offline feature snapshots with the
  rehydrated online store. Rebuild or quarantine any feature view that exceeds
  numeric or clock-skew tolerances.
- **Compliance audit** – Export PostgreSQL `orders`, `fills`, and
  `risk_events` to encrypted CSV for regulator-ready evidence. Archive to the
  immutable bucket with retention lock and log the checksum in
  `reports/disaster-recovery/`.

## Roles & Responsibilities Matrix

| Function | Primary Owner | Backup Owner | Responsibilities |
| --- | --- | --- | --- |
| Incident Commander | Staff SRE on-call | Head of Platform | Declare severity, coordinate recovery steps, maintain timeline and decision log. |
| Database Lead | Database Reliability Engineer | Data Platform Manager | Execute database failover, validate replication health, coordinate PITR restores. |
| Messaging Lead | Streaming Platform Engineer | Staff SRE | Manage Kafka/MirrorMaker state, verify ISR, ensure consumer offsets replay successfully. |
| Application Lead | Execution Platform TL | API Engineering TL | Redeploy workloads, validate order routing, coordinate feature flag toggles. |
| Observability Lead | Observability Engineer | SRE Analyst | Monitor dashboards, confirm alert fidelity, capture evidence for postmortem. |
| Communications Lead | Customer Success Director | Compliance Officer | Manage client/regulator comms, status page updates, internal briefings. |
| Security Liaison | Security On-Call | CISO Delegate | Validate credential posture, monitor for adversarial activity, approve Vault operations. |

## Communication & Escalation Plan

1. **Alerting Stack** – PagerDuty services `tradepulse-sre` and `tradepulse-security` auto-page SEV-1 rotations. Slack channel `#inc-dr` mirrors incident updates and houses the bot-run timeline.
2. **Stakeholder Updates** – Communications lead issues updates every 15 minutes to executives using the approved template in `docs/templates/incident_playbook.md` and refreshes the status page through the communications runbook in `docs/incident_playbooks.md`.
3. **Client Outreach** – Customer success maintains pre-approved messaging for key tiers (HFT, institutional, retail). Primary contact list is stored in the encrypted CRM export referenced in `docs/scenarios/client_contact_roster.csv`.
4. **Regulatory Notifications** – Compliance officer files regulatory notices (e.g., SEC Reg SCI) within mandated windows following the procedures captured in `docs/incident_playbooks.md`. Evidence and timestamps are appended to the incident ticket.
5. **Post-Recovery Briefing** – Within 2 hours of stabilization, deliver summary to leadership covering outage cause, duration, RPO/RTO achieved, and next steps.

## Training & Preparedness Drills

- **Onboarding Curriculum** – New SREs must complete the DR foundations module in the internal learning portal, pass the hands-on lab restoring PostgreSQL from PITR, and shadow one live failover simulation.
- **Biannual Certification** – Critical responders renew credentials by completing the DR practical exam scenario hosted in the staging control plane with success criteria of <20 minutes RTO in the lab environment.
- **Surprise Alerts** – Quarterly, issue unannounced drill pages during business hours to validate escalation chains and login readiness (Vault, cloud consoles, runbook access).
- **Knowledge Base Refresh** – Every sprint, service owners review linked runbooks for accuracy. Stale steps trigger doc updates tracked in the quality backlog.

## Critical Dependency Inventory

| Dependency | Classification | Redundancy Strategy | DR Verification |
| --- | --- | --- | --- |
| Cloud provider regions (Primary + Secondary) | Infrastructure | Multi-region deployment with Terraform parity modules; cross-region private networking | Monthly Terraform drift report + latency benchmarking |
| Market data vendors (Primary/Secondary) | External Service | Hot-standby feeds with adaptive load balancing via feature flags | Weekly heartbeat monitors + failover injection in chaos program |
| Brokerage/exchange connectivity | External API | Dual leased lines + VPN over internet backup; automatic route selection | Quarterly circuit failover test with mock orders |
| CI/CD control plane | Internal Platform | Git mirrors + ArgoCD warm standby | Nightly sync check + signature verification |
| Secrets management (Vault) | Security | Performance + DR clusters with replication | Monthly `vault operator dr failover` dry run |
| Observability stack | Monitoring | Multi-region Prometheus federation + replicated Loki/Tempo | Daily scrape parity job + on-call dashboards |
| Authentication/SSO | Identity | IdP redundant tenants with conditional access policies | Semi-annual failover exercise with security team |

Maintain this inventory in the Operational Handbook appendix and update any time a new dependency is introduced or retired.

## Return to Primary Region

1. **Root-Cause & Remediation** – Resolve the incident cause, verify no latent
   risks. Document in postmortem.
2. **Rebuild Primary** – Provision fresh infrastructure via Terraform, restore
   from latest backups, and rejoin replication (PostgreSQL `pg_basebackup`,
   Kafka `--sync-group-offsets`).
3. **Warm-up & Validation** – Execute synthetic load for 30 minutes; ensure RPO
   alignment by replaying change data capture to catch up.
4. **Planned Failback** – Follow the same steps as failover but in reverse,
   ensuring staggered cutover (Kafka first, then PostgreSQL, then workloads).
5. **Post-Failback Review** – Confirm replication healthy, remove temporary
   throttles, update incident log with final timelines.

## Tooling & Automation References

- `infra/terraform/` – Region templates, network, and database modules.
- `scripts/resilient_data_sync.py` – Hardened artifact transfer and checksum
  verification for restoring snapshots between regions.
- `scripts/runtime` – Shared primitives (progress, resumable transfers) used by
  DR automation workflows.
- `observability/dashboards/` – Grafana dashboards capturing replication lag,
  API SLOs, and queue depth vital to failover decisions.

## Documentation & Audit Requirements

- Update this runbook quarterly or after any material architecture change.
- Store signed PDF exports of each exercise and real incident review in
  `reports/disaster-recovery/`.
- Maintain contact roster (`docs/operational_readiness_runbooks.md`) with
  on-call rotations, vendor escalation paths, and regulator contacts.
- Enforce drift checks via CI to prevent configuration rot.

Failure to keep documentation current is a policy violation and triggers
compliance escalation.
