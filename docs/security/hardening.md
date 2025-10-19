# Security Hardening Program

This document codifies the end-to-end security hardening program for TradePulse.
It augments the global guidance in [`SECURITY.md`](../../SECURITY.md) with
operational processes, ownership, and control verification for the most
sensitive areas of the platform.

## Guiding Principles

1. **Layered defenses** – Every critical control must have at least one
   compensating safeguard to reduce single points of failure.
2. **Continuous verification** – Controls are verified through automated tests,
   observability, and manual reviews on a defined cadence.
3. **Explicit ownership** – Every control maps to a team and an accountable
   owner with published SLAs.
4. **Feedback loops** – Findings from scans, incidents, and exercises are fed
   into the backlog and influence architecture decisions.

## Threat Modeling Lifecycle

| Phase                | Activities                                                                 | Cadence             | Owner                 |
|----------------------|-----------------------------------------------------------------------------|---------------------|-----------------------|
| Scoping              | Update trust boundaries, data flow diagrams (DFDs), and asset inventory.   | Quarterly, and pre-release | Architecture Guild |
| Model + Analysis     | Apply STRIDE + MITRE ATT&CK mapping, build abuse cases, enumerate controls. | Quarterly           | Security Engineering  |
| Validation           | Peer review model, run attack-tree workshops, publish residual risk rating. | Within 2 weeks post-workshop | Security + Product |
| Tracking             | File remediation tasks, link to Threat Model ID in Jira, monitor burn down. | Continuous          | Respective owners     |

### Required Artifacts

- Data flow diagrams for each bounded context stored in
  `docs/architecture/system_overview.md`.
- Threat Model registry (Notion + Git-backed export under `docs/security/assets`).
- Attack trees for critical user journeys (`Place Order`, `Cancel Order`,
  `Strategy Deployment`) maintained via the `docs/security/assets/attack_trees` repo.
- Residual risk heatmap published to the monthly governance review.

### Automation

- `scripts/threatmodel/lint.py` (to be implemented) will validate that every
  component in the architecture catalog participates in at least one DFD.
- GitHub Action `threatmodel.yml` blocks merges lacking an updated threat model
  reference for ADRs or major features (flagged with label `security-review`).

## Attack Surface Management

1. **Inventory** – Maintain an authoritative list of:
   - Publicly routable endpoints (REST, gRPC, WebSocket, FIX) with authentication requirements.
   - Third-party integrations (exchanges, data vendors) including IP allowlists and credential scope.
   - Admin interfaces, feature flags, and background jobs.
   - Build/deploy pipelines and artifact registries.
2. **Classification** – Tag surfaces as `Tier0`, `Tier1`, or `Tier2` based on
   confidentiality/integrity/availability (CIA) impact.
3. **Change Detection** – Nightly job diffs Kubernetes ingress manifests,
   Terraform stacks, and API schema changes. Unknown additions trigger a P1 page.
4. **Validation** – Monthly external perimeter scans (Nmap + ProjectDiscovery
   `naabu` + `httpx`) with results cross-checked against inventory.
5. **Alerting** – Any orphaned surface (detected but not inventoried) must be
   shut down or onboarded within 72 hours.

## Fuzz Testing Strategy

| Target                     | Technique/Tooling                           | Trigger |
|----------------------------|---------------------------------------------|---------|
| Python parsers (`core/`)   | [Atheris](https://github.com/google/atheris) via `poetry run pytest --atheris` profile. | Nightly + pre-release |
| Rust market data adapters (`rust/feeds`) | `cargo fuzz` with libFuzzer harness. | Nightly + on change |
| gRPC/Protobuf schemas      | `protobuf-fuzz` generated harnesses executed in CI. | On schema change |
| Serialization boundaries (`interfaces/`) | Custom fuzzers using [`hypothesis`](https://hypothesis.works/) + grammar-based fuzzing. | PR gated |

Operational requirements:

- Fuzzing CI jobs must enforce a minimum of **30 minutes** runtime for nightly
  builds and **5 minutes** for PRs with sanitizer instrumentation enabled.
- Corpus and crash artifacts stored in `s3://tradepulse-security-fuzzing/<target>`.
- The owning team triages new crashes within **24 hours**; blocking issues are
  filed with severity `S0`.
- Coverage reports ingested into the security dashboard; target is ≥ 80%
  structured input coverage for protocol handlers.

## Static Application Security Testing (SAST)

| Tool      | Scope                           | Blocking Criteria |
|-----------|---------------------------------|-------------------|
| CodeQL    | `src/`, `core/`, `backtest/`, Go services | Any finding ≥ `High` severity blocks merge. |
| Semgrep   | Monorepo (`--config=auto` + custom rules under `configs/security/semgrep`) | `High` severity blocks merge; `Medium` surfaces review. |
| Bandit    | Python security linting         | `B` level or higher blocks merge. |
| Gosec     | `go/` directory                 | `High` severity blocks merge. |

Implementation notes:

- SAST runs on every PR and nightly on `main` with SARIF uploads.
- Baseline suppression files (`.sarif-baseline`) require security approval.
- Findings triage SLA: Critical – 24h, High – 3d, Medium – 5d, Low – 10d.
- The `security/static-analysis` dashboard tracks mean-time-to-remediate (MTTR).

## Dynamic Application Security Testing (DAST)

- **Tools**: OWASP ZAP baseline for REST/UI, `zap-full-scan` for authenticated
  staging, `grpcurl` + custom scripts for gRPC endpoints.
- **Pipeline**: Nightly scan of staging, scheduled weekend scan of production
  (read-only tests), PR-triggered smoke scans for API schema changes.
- **Coverage**: Ensure authenticated contexts exercise all critical workflows
  (order lifecycle, portfolio management, admin tasks). Use HAR files generated
  from Cypress end-to-end tests as ZAP input.
- **Gating**: Critical findings block deployment; high severity requires
  security sign-off with compensating controls.
- **Reporting**: SARIF + HTML artifacts retained for 90 days in `reports/dast/`.

## Dependency Security & Supply Chain

- Lock files (`requirements.lock`, `requirements-dev.lock`, `poetry.lock`, `go.sum`)
  remain immutable; updates go through the monthly patch window unless a
  security advisory triggers an emergency patch.
- Run `make security-audit` (pip-audit + safety) and `make supply-chain-verify`
  on every PR touching dependencies.
- Maintain a deny/allow list under `configs/security/denylist.yaml` and
  `configs/security/allowlist.yaml`.
- Artifact provenance: All containers signed with Sigstore Cosign, provenance
  attested via SLSA v3 GitHub generator.
- SBOMs (CycloneDX 1.5) generated on PR + release and published to
  `reports/sbom/`.
- External dependency monitoring via OSS Index with alerting into Security Ops.

## Resource Limiting & Runtime Safety

- **Kubernetes**: Every workload must declare CPU/Memory `requests` and `limits`
  with ratios < 2x. Example baseline for trading APIs:
  ```yaml
  resources:
    requests:
      cpu: "500m"
      memory: "512Mi"
    limits:
      cpu: "1"
      memory: "768Mi"
  ```
- **Kernel controls**:
  - `ulimit -n 65536` for high-throughput services with monitoring for leaks.
  - `RLIMIT_CORE` disabled in production to avoid sensitive dumps.
  - Enable `prctl(PR_SET_NO_NEW_PRIVS, 1)` for all containers.
- **Job isolation**: Backtest workers run inside gVisor or Kata Containers
  sandboxes with seccomp profiles derived from `configs/security/seccomp.json`.
- **Rate limiting**: Enforce per-tenant quotas via Envoy filters (`1000 req/min`
  per strategy) with adaptive concurrency to mitigate DoS.

## Sandboxing Controls

- Enforce AppArmor profiles for Kubernetes pods (`apparmor.security.beta.kubernetes.io` annotations).
- Use `seccompProfile` set to `RuntimeDefault` for generic workloads, and a
  custom profile for order execution pods (kept in `configs/security/seccomp/order-exec.json`).
- Adopt `podSecurity` admission in `enforce` mode (baseline profile) with
  mutation webhook to reject privileged pods.
- Run Jupyter notebooks inside isolated namespaces with network egress blocked
  by default; egress only via approved bastion service.

## Network Policies & Segmentation

- Zero-trust network baseline using Kubernetes `NetworkPolicy` per namespace.
- East-west traffic restricted to service-to-service allowlists stored in
  `configs/network/policies/` and generated via IaC.
- Use service mesh (Linkerd/Istio) mTLS with workload identities minted by SPIRE.
- Edge security groups restrict ingress to known CIDR ranges; egress only via
  NAT gateways with logging.
- Quarterly firewall review verifying least privilege and alignment with asset
  classification.

## Web Application Firewall (WAF) & Request Content Controls

- Deploy managed WAF (AWS WAF / Cloudflare) with:
  - Core OWASP ruleset, bot management, and rate-based rules.
  - Custom rules for trading-specific abuse (order stuffing, symbol abuse).
  - Geofencing for admin surfaces.
- Integrate WAF logs into SIEM; alerts on anomaly scores > 50.
- API Gateway schema validation enforcing JSON Schema / Protobuf definitions
  generated from `schemas/` repo, rejecting requests with:
  - Unknown fields
  - Size > configured thresholds (`payload_max_bytes` per endpoint)
  - Malformed encodings
- Implement payload inspection for binary protocols (FIX) using an inline
  decoder to enforce message grammar and throttle invalid attempts.

## Access Logging & Telemetry

- All ingress/egress requests emit structured JSON logs containing:
  - `request_id`, `user_id`, `tenant_id`
  - `source_ip`, `user_agent`
  - `auth_method`, `scopes`
  - `latency_ms`, `status_code`, `response_size`
  - `rate_limit_bucket`, `waf_action`
- Logs shipped via OpenTelemetry to the centralized SIEM with immutability
  controls (write-once object storage, 400-day retention).
- Tamper detection: Daily hash-chain verification and integrity alerts.
- Sensitive actions (withdrawals, strategy modifications) produce audit events
  ingested into the compliance lake with real-time alerts on anomalous patterns.

## Workforce Enablement & Training

- **Onboarding**: Mandatory secure coding + threat modeling training within the
  first 30 days.
- **Annual certification**: All engineers renew OWASP Top 10, secure coding, and
  cloud security training (tracked in LMS).
- **Quarterly workshops**: Hands-on labs covering exploitation of past bugs,
  secure dependency management, and secrets handling.
- **Purple team drills**: Security and engineering pair to review recent
  findings, live patching exercises, and configuration hardening labs.
- Training completion is a prerequisite for production access.

## Incident Response Exercises

- **Tabletop drills**: Bi-monthly scenario-based exercises (e.g., exchange API
  compromise, insider data exfiltration). Document outcomes in
  `docs/incident_playbooks.md` appendices.
- **Live-fire simulations**: Quarterly chaos-security exercises combining fault
  injection with simulated adversary behavior.
- **After-action reviews**: Captured in the incident knowledge base with
  remediation backlog items tagged `incident-retro`.
- **Metrics**: Track detection time, response time, communication efficacy, and
  control gaps discovered during drills.

## Governance & Metrics

- Security scorecard reviewed monthly, covering:
  - % of systems with up-to-date threat models.
  - SAST/DAST MTTR and backlog size.
  - Dependency vulnerability age distribution.
  - Sandbox and network policy coverage.
  - Training completion rates.
  - Tabletop/live-fire exercise outcomes.
- Executive summary published to the Risk Committee with red/amber/green status.

## Implementation Backlog Snapshot

1. Automate threat model linting (`scripts/threatmodel/lint.py`).
2. Expand fuzzing harnesses for FIX parser (`interfaces/fix/`).
3. Complete roll-out of custom seccomp profiles for execution pods.
4. Integrate AWS WAF traffic logs with anomaly detection playbooks.
5. Launch quarterly live-fire exercises with red team support.

