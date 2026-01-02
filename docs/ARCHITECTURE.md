# Architecture Blueprint

## Purpose and Scope

TradePulse orchestrates quantitative research, signal generation, and execution services under a contracts-first
mandate. This blueprint captures the current 2025 architecture baseline that all domain, application, and
infrastructure teams align to when planning enhancements, incident response, or compliance audits.
It complements the deep-dive assets located in [`docs/architecture/`](architecture/) and is reviewed every
release train by the architecture review board.
Application-layer orchestration, bootstrap, and secret/security controls are detailed in
[`architecture/application_layer.md`](architecture/application_layer.md).

## Capability Pillars

| Pillar | Core Responsibilities | Primary Owners | Key Interfaces |
| --- | --- | --- | --- |
| **Market Intelligence** | Acquisition of market, alternative, and internal risk data; feature computation; catalog governance. | Data Platform Guild | `core.ingestion`, `core.features`, gRPC ingestion facade, Kafka/Redpanda topic schema contracts. |
| **Decisioning & Alpha** | Strategy lifecycle, simulation sandbox, feature orchestration, policy routing. | Quant Systems Guild | `strategies.*`, `core.simulation`, protobuf strategy contracts, policy evaluation engine. |
| **Execution Fabric** | Order routing, liquidity adapters, risk throttles, reconciliation, FIX/REST translation. | Execution Guild | `execution.gateway`, `execution.adapters.*`, FIX bridge, REST control plane. |
| **Observability & Control** | Monitoring, SLO budgets, guardrails, compliance audit trail, operational runbooks. | Reliability Guild | Telemetry mesh (`observability.agent`), policy engine, governance APIs, incident playbooks. |
| **Experience Layer** | Web dashboards, CLI, partner APIs, notification channels. | Product Experience Guild | Next.js dashboard, CLI (`tradepulse`), gRPC-web gateway, Webhook broker. |

Each pillar maintains an explicit backlog and architectural runway captured in the [Architecture Review Program](architecture/architecture_review_program.md).

## Service Topology

| Service / Package | Language & Runtime | Deployment Model | Upstream Dependencies | External Interfaces |
| --- | --- | --- | --- | --- |
| `tradepulse-api` | Python 3.11 (FastAPI) | Kubernetes deployment (`deploy/tradepulse-deployment.yaml`, `deploy/kustomize/base`) | OAuth2 issuer + JWKS, audit secret store, mTLS trust bundle | HTTPS/REST (`:8000`), Prometheus metrics (`:8001`) |
| `admin` | Python 3.11 (FastAPI admin control) | Helm chart (`deploy/helm/tradepulse/charts/admin`) | Cluster admin secrets, audit logging policies | HTTP admin API (`:8000`) |
| `sandbox` | Python 3.11 (sandbox harness) | Helm chart + HPA (`deploy/helm/tradepulse/charts/sandbox`) | Optional OpenTelemetry endpoint | HTTP API (`:8080`), health/ready probes |
| `observability-stack` | OpenTelemetry Collector + Prometheus + Grafana | Helm chart (`deploy/helm/tradepulse/charts/observability`) | Service monitors, metrics/log pipelines | OTLP ingest, dashboards & alerting |

Cross-cutting concerns such as authentication, tracing headers, and deployment safety are validated through
the GitHub Actions workflows in `.github/workflows/` (notably `ci.yml`, `pr-release-gate.yml`,
`publish-image.yml`, and `helm.yml`) alongside the guidance in
[`docs/github_actions_automation.md`](github_actions_automation.md).

## Module Boundaries and Contracts

| Module | Contract Surface | Allowed Dependencies | Versioning & Gates |
| --- | --- | --- | --- |
| `core/` | Domain models, feature pipelines, compliance primitives, and shared DTOs with schemas in [`schemas/events/`](../schemas/events/) | None (foundation) | SemVer (`core.api.v1`); breaking changes require major bump + compatibility shims |
| `backtest/` | Simulation driver interfaces in [`interfaces/backtest.py`](../interfaces/backtest.py) and workflow harnesses in [`backtest/`](../backtest/) | `core/` | SemVer (`backtest.api.v1`); runs behind CI contract tests |
| `execution/` | Order lifecycle orchestration, adapters, OMS/routing, and risk control surfaces defined in [`interfaces/execution/`](../interfaces/execution/) | `core/` | SemVer (`execution.api.v1`); adapter contracts must stay backward compatible |
| `runtime/` | Runtime safety controls (kill switch, thermo control, recovery) and live runner interfaces in [`interfaces/live_runner.py`](../interfaces/live_runner.py) | `core/`, `execution/` | SemVer (`runtime.api.v1`); release gates run integration + property suites |
| `observability/` | Metrics/logging/tracing, release gate telemetry, and dashboards in [`observability/`](../observability/) | `core/` (telemetry types only) | SemVer (`observability.telemetry.v1`); trace/metric shape changes require dual approval |
| `ui/dashboard/` | gRPC-web/GraphQL DTOs derived from [`schemas/openapi/tradepulse-online-inference-v1.json`](../schemas/openapi/tradepulse-online-inference-v1.json) | Consumes only published APIs (no private imports) | Follows API SemVer; UI build blocks on schema diff |
| `tacl/` | Thermodynamic control hooks in [`tacl/`](../tacl/) + [`runtime/thermo_controller.py`](../runtime/thermo_controller.py); pre-action risk gating in [`tacl/risk_gating.py`](../tacl/risk_gating.py) | `runtime/`, `observability/` | SemVer (`tacl.control.v1`); adaptations blocked unless compatibility matrix passes |

Links use `../` because this document lives under `docs/`; they resolve to the repo-root `schemas/`, `interfaces/`, and module directories listed above.

### Dependency & Event Graph (high level)
- `core` publishes normalized market events → consumed by `backtest` and `execution`.
- `runtime` orchestrates `execution` adapters and routes policy decisions from `strategies/` through the `core` DTOs.
- `observability` passively consumes metrics/traces/logs from every module; no reverse imports allowed.
- `tacl` subscribes to latency/coherency/cost metrics and can only actuate `runtime` via the control API with human-approved gates.

Schema and API diagrams live in [`docs/architecture/system_overview.md`](architecture/system_overview.md); any cross-module change must update the relevant schema version and cross-reference the change in [`DOCUMENTATION_SUMMARY.md`](../DOCUMENTATION_SUMMARY.md).

## Data and Knowledge Fabric

| Layer | Technologies | Durability Strategy | Notes |
| --- | --- | --- | --- |
| **Hot Path Cache** | Redis Cluster, in-memory ring buffers | Multi-AZ replication + replica lag alarms | Drives signal latency below 25 ms for execution-critical reads. |
| **Operational Store** | PostgreSQL 16 with temporal tables | PITR with 5 minute RPO, daily logical dump | Houses governance metadata, order state machines, and audit relationships. |
| **Analytical Lakehouse** | Iceberg on S3-compatible object storage | Hourly snapshot manifests + schema versioning | Retains tick history, enriched features, and research artefacts. |
| **Feature Store** | Feast + Redis/Parquet hybrid | Online/offline parity verification nightly | Documents [here](architecture/feature_store.md). |
| **Knowledge Graph** | Neo4j AuraDS | Continuous backup stream + weekly consistency check | Tracks dependency lineage across signals, policies, and deployments. |

Data contracts are catalogued in [`docs/schemas/`](schemas/) with quality gates governed by the
[Documentation Standardisation Playbook](documentation_standardisation_playbook.md),
[Quality Gates](quality_gates.md), and the operational data governance rules in
[DATA_GOVERNANCE.md](DATA_GOVERNANCE.md).

## Runtime Interaction Overview

1. **Acquisition** – `ingestion-orchestrator` validates source payloads, stamps governance metadata, and publishes
enriched events onto the shared Redpanda bus.
2. **Feature Materialisation** – `feature-store-writer` normalises events into the lakehouse and feature store,
updating catalog states that are surfaced through the UI hub and CLI.
3. **Strategy Evaluation** – Quant strategies subscribe through the simulation scheduler and policy engine,
producing signed signals that honour [`domain/`](../domain/) invariants.
4. **Execution Loop** – The execution gateway enforces risk budgets, liaises with broker adapters, and persists
trade lifecycle updates back to the operational store.
5. **Safety Gating** – The runtime runner injects a pre-action filter into `execution.live_loop` to enforce
threat-model constraints on volatility, liquidity, latency, and policy deviation; breaches trigger safe-mode
policy routing (conservative) or emergency rollback of outstanding orders.
6. **Feedback & Oversight** – Telemetry collectors, SLO dashboards, and governance hooks feed incidents,
runbooks, and compliance reports found in [`docs/operational_handbook.md`](operational_handbook.md).

Sequence and data flow diagrams backing this narrative are maintained in
[`docs/architecture/system_overview.md`](architecture/system_overview.md).

## Neuro-primitive Catalog

TradePulse exposes a small set of neuro-inspired primitives that are treated as reusable control blocks across
learning and decision loops. Each primitive is defined by a narrow contract, strict observability, and minimal
cross-module dependencies.

| Primitive | Core Role | Integration Surface |
| --- | --- | --- |
| **Modulation-signal controller** | Computes a risk-weighted learning-rate modulation signal (e.g., lowering policy/value update scale under high RPE or threat while allowing arousal to boost learning). | `rl/core/modulation_signal.py` applies modulation to the policy/value update loop and emits modulation telemetry via the RL metrics gauges. |

## Quality Attributes and Guardrails

- **Scalability:** Horizontal pod autoscaling (HPA/KEDA) limits defined per service with SLO-backed alerts
  documented in [`docs/reliability.md`](reliability.md).
- **Resilience:** Circuit breakers, bulkheads, and chaos drills scheduled via
  [`docs/resilience.md`](resilience.md); failover procedures detailed in the runbooks directory.
- **Security:** Identity, encryption, and least privilege controls centralised in
  [`docs/security/architecture.md`](security/architecture.md) with enforcement automated through
  the secrets management pipelines.
- **Compliance:** Trade surveillance, retention, and audit obligations referenced in
  [`docs/governance.md`](governance.md) and incident playbooks.
- **Documentation:** Every architectural change must include updates to this blueprint, affected diagrams,
  and cross-references tracked in [`DOCUMENTATION_SUMMARY.md`](../DOCUMENTATION_SUMMARY.md).

## Change Management & Documentation Map

| Lifecycle Stage | Required Artefacts | Approval Checkpoint |
| --- | --- | --- |
| **Exploration** | Architecture decision record draft (see [`docs/adr/`](adr/)), prototype diagrams. | Architecture review board triage. |
| **Implementation** | Updated service topology, schema migrations, feature toggles, new runbooks. | Release readiness review + reliability sign-off. |
| **Post-Launch** | Telemetry dashboards, incident retrospectives, documentation gap review. | Governance committee and product owner sign-off. |

Refer to the [Documentation Information Architecture](documentation_information_architecture.md) for
navigation patterns, ownership, and versioning rules across the wider knowledge base.

## Conceptual Architecture Visualization

For a comprehensive visual guide to TradePulse conceptual elements and their relationships, including detailed
diagrams of neuromodulation systems, TACL thermodynamic control, and signal lifecycle, see the
[Conceptual Architecture (Ukrainian)](CONCEPTUAL_ARCHITECTURE_UA.md) document and the
[Architecture Diagrams](architecture/assets/README.md) catalog.
