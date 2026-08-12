# GeoSync Technical Audit (2025-01)

## Executive Summary
- Conducted a focused review of application services, infrastructure-as-code, CI/CD automation, and runtime dependencies.
- Identified critical security exposures in the default infrastructure topology and observability stack that could allow control-plane takeover or log tampering if deployed as-is.
- Flagged reliability and process gaps where safety controls (kill switch durability, coverage enforcement, dependency pinning) are not aligned with stated standards.
- Proposed a phased roadmap with accountable owners, success metrics, and interim milestones to drive remediation without disrupting current delivery commitments.

## Methodology
1. **Source review** – Examined core service configuration, domain logic, and operational tooling under `application/`, `core/`, and `observability/`.
2. **Infrastructure review** – Audited Terraform EKS baseline and container orchestration assets in `infra/terraform/eks` and `docker-compose.yml`.
3. **Process review** – Evaluated CI/CD pipelines, coverage thresholds, and dependency policies defined in `pyproject.toml` and GitHub workflows.
4. **Risk assessment** – Assessed impact, likelihood, and blast radius for each finding; scored effort to inform prioritisation.

## Key Findings

### 1. EKS control plane is publicly reachable by default
- **Evidence:** Terraform enables both public and private API endpoints (`cluster_endpoint_public_access = true`).【F:infra/terraform/eks/main.tf†L62-L83】
- **Impact:** High – exposes Kubernetes API to the internet; exploitation could yield full cluster compromise.
- **Effort:** Medium – requires updating module inputs, security groups, and bastion/peering strategy.
- **Risk:** High – direct ingress point to production control plane.
- **Recommendation:** Disable public endpoint, enforce private access via VPN/DirectConnect, and add fine-grained CIDR allow-listing.

### 2. Observability stack disables Elastic security and mounts Docker socket
- **Evidence:** `docker-compose` sets `xpack.security.enabled=false` for Elasticsearch and runs Filebeat with root + Docker socket access.【F:docker-compose.yml†L26-L52】
- **Impact:** High – unauthenticated access to logs and potential container breakout through the Docker socket.
- **Effort:** Medium – requires enabling TLS/auth in Elastic stack and introducing least-privilege log shipping.
- **Risk:** High – compromises could leak trading telemetry or allow lateral movement.
- **Recommendation:** Enable Elastic security, rotate credentials via secrets manager, and remove the raw Docker socket mount in favor of read-only log shipping sidecars or Fluent Bit.

### 3. Kill-switch persistence defaults to ephemeral local SQLite
- **Evidence:** Admin API settings persist critical kill-switch state to `state/kill_switch_state.sqlite` when Postgres is not configured.【F:application/settings.py†L70-L112】
- **Impact:** Medium – restarts or container migrations risk losing emergency shutdown state, undermining safety controls.
- **Effort:** Medium – requires mandating durable Postgres backend and provisioning managed storage.
- **Risk:** Medium – introduces recovery gaps during outages or failovers.
- **Recommendation:** Make Postgres persistence mandatory in production, enforce migrations in CI, and mount durable volumes for local/dev use.

### 4. Coverage policy drift between tooling and CI
- **Evidence:** Repository enforces 90% coverage via configuration but CI pipeline only fails below 80%.【F:pyproject.toml†L102-L117】【F:.github/workflows/ci.yml†L31-L44】
- **Impact:** Medium – allows regressions that violate documented quality bar to merge unnoticed.
- **Effort:** Low – update CI coverage threshold or align configuration.
- **Risk:** Medium – reduced test signal increases defect escape probability.
- **Recommendation:** Raise CI `--cov-fail-under` to 90% or centralise threshold via config to eliminate divergence.

### 5. Runtime dependencies are not fully pinned
- **Evidence:** Core dependencies in `pyproject.toml` use open-ended `>=` constraints without upper bounds or lock enforcement.【F:pyproject.toml†L22-L62】
- **Impact:** Medium – supply-chain risk from unreviewed upstream releases; reproducibility suffers across environments.
- **Effort:** Medium – requires generating lock files and enforcing them in CI/CD.
- **Risk:** Medium – opportunistic attackers could exploit automatic upgrades; unexpected ABI/API changes can break production.
- **Recommendation:** Adopt deterministic lock files (`pip-compile` outputs), publish artifact checksums, and gate deployments on signature and hash verification.

## Prioritised Remediation Backlog
| Priority | Finding | Impact | Effort | Owner | Metric |
| --- | --- | --- | --- | --- | --- |
| P0 | Secure EKS control plane | High | Medium | Platform Engineering | Public endpoint disabled; API reachable only via private CIDRs |
| P0 | Harden Elastic/Filebeat deployment | High | Medium | SRE / SecOps | Authenticated Elastic endpoints; Docker socket unmounted |
| P1 | Enforce durable kill-switch store | Medium | Medium | Risk Engineering | Kill-switch DB hosted on HA Postgres; failover test pass |
| P1 | Align coverage gate with policy | Medium | Low | QA Automation | CI fails <90% coverage across modules |
| P2 | Enforce dependency pinning | Medium | Medium | Build Engineering | Lock files committed; CI verifies `pip-compile` parity |

## Remediation Roadmap

### Phase 1 – Containment (Weeks 0-2)
- **Secure EKS endpoint** (Owner: Platform Engineering)
  - Disable public endpoint, add security group ingress for VPN CIDRs.
  - **Deadline:** 2 weeks.
  - **Metric:** AWS Config rule `EKS_ENDPOINT_NO_PUBLIC` passes; kubectl access requires bastion.
  - **Milestone:** Change request approved; Terraform plan reviewed and applied in staging.
- **Elastic/Filebeat hardening** (Owner: SRE / SecOps)
  - Enable TLS/auth, provision credentials via secrets manager, replace Docker socket with log driver.
  - **Deadline:** 2 weeks.
  - **Metric:** Automated security scan validates TLS; container scan passes without privileged mounts.
  - **Milestone:** Hardened stack validated in staging.

### Phase 2 – Resilience (Weeks 3-5)
- **Kill-switch persistence uplift** (Owner: Risk Engineering)
  - Provision managed Postgres, migrate kill-switch schema, add failover tests.
  - **Deadline:** 5 weeks.
  - **Metric:** Chaos test proves kill-switch survives pod restarts; RPO ≤ 1 minute.
  - **Milestone:** Runbook updated; audit log shows successful failover drill.
- **Coverage gate alignment** (Owner: QA Automation)
  - Raise CI threshold to 90%, integrate badge/reporting.
  - **Deadline:** 3 weeks.
  - **Metric:** CI fails below 90%; dashboard trends tracked sprintly.
  - **Milestone:** Retro confirms enforcement without build instability.

### Phase 3 – Sustainability (Weeks 6-9)
- **Dependency governance** (Owner: Build Engineering)
  - Generate lock files, integrate supply-chain verification, set up dependabot grouping.
  - **Deadline:** 9 weeks.
  - **Metric:** CI validates lock drift; SBOM regenerated with signed artifacts.
  - **Milestone:** Release checklist updated; first locked release shipped.

## Additional Opportunities
- Automate periodic penetration testing of admin endpoints once TLS/auth hardening completes.
- Introduce synthetic kill-switch checks into observability stack for continuous verification.
- Expand policy-as-code coverage (e.g., Terraform Cloud/OPA) to catch misconfiguration earlier in development.
