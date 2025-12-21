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
| `ingestion-orchestrator` | Go 1.22 | Kubernetes (stateful set) | Schema registry, Redpanda, feature store writer | Kafka topics, REST admin API |
| `feature-store-writer` | Rust (tokio) | Kubernetes (deployment) | Object store (S3 compatible), Postgres metadata DB | gRPC (`features.v1.Writer`), metrics exporter |
| `simulation-scheduler` | Python 3.11 (FastAPI) | Kubernetes (deployment + Keda) | Redis queue, feature store, experiment tracker | REST control plane, gRPC event stream |
| `execution-gateway` | Go 1.22 | Bare metal + sidecar proxies | Order book cache, policy service, market adapters | FIX 4.4, REST broker APIs, WebSocket status feed |
| `policy-engine` | Python 3.11 (async worker) | Kubernetes (deployment) | Redis, governance DB | gRPC (`governance.v1.Policy`), audit log sink |
| `telemetry-collector` | Rust (axum) | Kubernetes (daemon set) | Prometheus, Loki, OpenTelemetry collector | OTLP gRPC, JSON logging sink |
| `ui-hub` | Next.js 14 (Node 20) | Vercel / container image | gRPC-web gateway, metrics API | HTTPS, WebSocket notifications |

Cross-cutting concerns such as authentication, tracing headers, and protobuf compatibility are validated through
continuous integration pipelines defined in [`docs/github_actions_automation.md`](github_actions_automation.md).

## Data and Knowledge Fabric

| Layer | Technologies | Durability Strategy | Notes |
| --- | --- | --- | --- |
| **Hot Path Cache** | Redis Cluster, in-memory ring buffers | Multi-AZ replication + replica lag alarms | Drives signal latency below 25 ms for execution-critical reads. |
| **Operational Store** | PostgreSQL 16 with temporal tables | PITR with 5 minute RPO, daily logical dump | Houses governance metadata, order state machines, and audit relationships. |
| **Analytical Lakehouse** | Iceberg on S3-compatible object storage | Hourly snapshot manifests + schema versioning | Retains tick history, enriched features, and research artefacts. |
| **Feature Store** | Feast + Redis/Parquet hybrid | Online/offline parity verification nightly | Documents [here](architecture/feature_store.md). |
| **Knowledge Graph** | Neo4j AuraDS | Continuous backup stream + weekly consistency check | Tracks dependency lineage across signals, policies, and deployments. |

Data contracts are catalogued in [`docs/schemas/`](schemas/) with quality gates governed by the
[Documentation Standardisation Playbook](documentation_standardisation_playbook.md) and
[Quality Gates](quality_gates.md).

## Runtime Interaction Overview

1. **Acquisition** – `ingestion-orchestrator` validates source payloads, stamps governance metadata, and publishes
enriched events onto the shared Redpanda bus.
2. **Feature Materialisation** – `feature-store-writer` normalises events into the lakehouse and feature store,
updating catalog states that are surfaced through the UI hub and CLI.
3. **Strategy Evaluation** – Quant strategies subscribe through the simulation scheduler and policy engine,
producing signed signals that honour [`domain/`](../domain/) invariants.
4. **Execution Loop** – The execution gateway enforces risk budgets, liaises with broker adapters, and persists
trade lifecycle updates back to the operational store.
5. **Feedback & Oversight** – Telemetry collectors, SLO dashboards, and governance hooks feed incidents,
runbooks, and compliance reports found in [`docs/operational_handbook.md`](operational_handbook.md).

Sequence and data flow diagrams backing this narrative are maintained in
[`docs/architecture/system_overview.md`](architecture/system_overview.md).

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
