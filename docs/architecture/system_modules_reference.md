---
owner: docs@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
title: GeoSync System Modules Reference
---

# GeoSync System Modules Reference

## Purpose
This reference formalises the major functional modules that make up the GeoSync platform.
It is written for engineers, quantitative researchers, site reliability teams, product owners,
and governance stakeholders who need a shared, auditable vocabulary for the system. Each
module description clarifies what the module does, who depends on it, and the operational
problems it resolves so that domain roadmaps, onboarding plans, and regulatory artefacts can
align on the same mental model.

## Module Landscape at a Glance
| Module | What it is | Primary consumers | Problems solved |
| --- | --- | --- | --- |
| Data Fabric (`core/data`) | Unified ingestion, validation, and lineage tooling for all market data and derived features. | Data engineers, research scientists, analytics platform teams. | Safe onboarding of market feeds, schema drift protection, reproducible artefact tracking. |
| Market Intelligence Engine (`core/indicators`, `core/metrics`) | Advanced signal processing stack that extracts regime-aware features from time series. | Quant researchers, strategy designers, risk analysts. | Detects coherent market phases, surfaces curvature anomalies, quantifies microstructure health. |
| Strategy Orchestration (`core/strategies`) | Contract-driven runtime that wires analytical modules into executable trading strategies. | Quant developers, automated strategy ops, experimentation teams. | Guarantees input/output compatibility, enforces mode controls, normalises signal payloads. |
| Execution & Risk Controls (`execution/risk`, `execution/resilience`, `src/risk`) | Exchange-facing protection layer that enforces risk limits, kill-switch policies, and resiliency patterns. | Execution engineers, risk officers, operations desk. | Stops limit breaches, coordinates kill-switch engagement, isolates venue instabilities. |
| Event & Messaging Fabric (`core/events`, `core/messaging`) | Canonical schema definitions plus transport adapters for the event-driven backbone. | Platform integration teams, downstream data consumers, observability teams. | Maintains schema contracts, ensures idempotent fan-out, provides dead-letter handling. |
| Observability & Governance Utilities (`core/utils`) | Structured logging, metrics, and tracing primitives that make system decisions explainable. | SRE, compliance, platform governance. | Produces audit-ready telemetry, propagates correlation IDs, enforces SLO instrumentation. |

## Data Fabric (`core/data`)
**What it is.** The data fabric is the foundation for every market and research signal ingested
into GeoSync. Modules such as `core/data/ingestion.py` provide exchange adapters and secure
filesystem guards for historical and live feeds, while `core/data/quality_control.py` and
`core/data/validation.py` codify declarative quality gates, temporal contracts, and error
classes for resilient pipelines. The lineage of every generated artefact is tracked via the
`DataVersionManager` in `core/data/versioning.py`, ensuring the platform can reproduce
research outputs down to the exact snapshot.

**Who depends on it.**
- Data engineers rely on the ingestion guardrails to connect venues without risking polluted
  storage.
- Quant researchers use the validated frames and feature catalogues as trustworthy inputs to
  their experiments.
- Governance teams depend on the deterministic versioning trail to answer compliance requests.

**Problems it solves.**
- Prevents malformed CSV batches or websocket payloads from ever entering the system by
  enforcing schema and range checks before persistence.
- Normalises timestamps, symbol metadata, and instrument types so downstream analytics can
  remain venue-agnostic.
- Writes explicit artefact manifests that satisfy reproducibility demands during audits and
  model approvals.

## Market Intelligence Engine (`core/indicators`, `core/metrics`)
**What it is.** GeoSync’s intelligence stack couples multi-scale synchronisation analytics,
Ricci curvature diagnostics, and entropy measures to produce regime-aware signals. The
`GeoSyncCompositeEngine` in `core/indicators/kuramoto_ricci_composite.py` fuses Kuramoto
oscillator consensus with temporal Ricci flow and topology transition scores to emit
risk-calibrated entry, exit, and confidence guidance. Supporting modules—`core/indicators/cache.py`,
`core/indicators/pipeline.py`, and microstructure utilities in `core/metrics/__init__.py`—sustain
a library of reusable transforms that can be orchestrated with deterministic caching.

**Who depends on it.**
- Quant researchers pull composite signals to drive hypothesis testing and feature selection.
- Strategy developers connect the engine’s structured outputs to execution contracts without
  needing to re-implement complex geometry.
- Risk analysts reference the dominance timeframes and curvature diagnostics to reason about
  stress events.

**Problems it solves.**
- Detects emergent market phases with tunable confidence scoring, improving signal-to-noise
  ratios for systematic strategies.
- Quantifies cross-scale coherence and curvature shifts so teams can calibrate hedging and
  de-risking tactics ahead of transitions.
- Maintains idempotent signal history for replay, monitoring, and audit scenarios where the
  provenance of each trade recommendation matters.

## Strategy Orchestration (`core/strategies`)
**What it is.** The strategy engine delivers a contract-first execution environment. Within
`core/strategies/engine.py`, IO contracts, strategy contexts, and signal dataclasses enforce
structural compatibility between analytical outputs and live routing. Mode transitions—live,
paper, paused—are explicitly modelled to protect operators from accidental state flips, while
risk advisories and cancellation objects provide a structured feedback loop to the execution
surface.

**Who depends on it.**
- Quant developers compose strategies by wiring modules that conform to shared IO contracts.
- Experimentation teams toggle paper/live modes to validate changes under deterministic
  conditions.
- Operations staff review structured strategy signals when triaging anomalies during market
  events.

**Problems it solves.**
- Eliminates ad-hoc payload conventions by centralising validation, reducing integration
  regressions between research and execution teams.
- Makes every emitted signal self-describing and traceable via immutable metadata wrappers,
  accelerating forensic analysis.
- Provides a safe state machine so deployments can roll forward or back without risking latent
  orders or stale signals.

## Execution & Risk Controls (`execution/risk`, `execution/resilience`, `src/risk`)
**What it is.** This control plane governs all trade submissions. The `RiskManager` stack in
`execution/risk/core.py` codifies per-instrument notional, position, and order-rate thresholds,
backed by persistent kill-switch state stores and quality gates. The resilience toolkit in
`execution/resilience/circuit_breaker.py` layers Hystrix-style circuit breakers and adaptive
rate limiters onto every venue interaction. The `RiskManagerFacade` in `src/risk/risk_manager.py`
exposes these primitives to administrative surfaces and operational tooling without duplicating
state.

**Who depends on it.**
- Execution engineers embed the guardrails directly into exchange adapters.
- Risk officers receive deterministic breach handling and persisted rationales for every
  kill-switch activation.
- Operations desks leverage the facade to interrogate and reset controls during live events.

**Problems it solves.**
- Blocks orders that would violate policy-defined exposure caps before they ever reach an
  exchange, closing a major regulatory gap.
- Persists kill-switch state with ISO-8601 timestamps so incident responders can reconstruct
  the full timeline of any trading halt.
- Absorbs venue outages and latency spikes through circuit breakers and token buckets,
  preventing cascading failures across strategies.

## Event & Messaging Fabric (`core/events`, `core/messaging`)
**What it is.** The messaging fabric is the platform’s contract for event-driven integration.
`core/events/models.py` defines canonical Pydantic schemas for ticks, bars, signals, orders, and
fills with enumerated fields that downstream teams can rely on. On the transport side,
`core/messaging/event_bus.py` provides topic metadata, idempotency stores, and backend-specific
publish/subscribe scaffolding for Kafka or NATS deployments. Together they deliver a coherent,
replayable stream architecture with first-class retry and dead-letter semantics.

**Who depends on it.**
- Platform integration teams subscribe to strongly typed streams without writing defensive
  parsing logic.
- Downstream analytics teams ingest the same events for BI dashboards and regulatory archives.
- Observability engineers hook into retry topics and DLQs to monitor systemic health.

**Problems it solves.**
- Guarantees schema compatibility through generated models so versioning is explicit and
  backwards compatibility is testable.
- Embeds idempotency controls in the transport layer, eliminating duplicate side effects during
  retries or consumer restarts.
- Encapsulates topic naming, partitioning, and security configuration so deployments remain
  consistent across environments.

## Observability & Governance Utilities (`core/utils`)
**What it is.** Observability primitives live in `core/utils/logging.py`, `core/utils/metrics.py`,
and adjacent helpers. Structured JSON logging automatically enriches records with correlation
IDs, tracing spans, and extra metadata, while timing context managers deliver latency
breakdowns as part of every log event. Metrics collectors expose Prometheus-friendly counters
and histograms so SLOs in the operational runbooks remain actionable.

**Who depends on it.**
- Site reliability engineers use the consistent telemetry format to build dashboards and
  automate alerting.
- Compliance and governance stakeholders review machine-readable logs that tie every decision
  back to a trace ID.
- Product owners and programme leads use exported metrics to track feature adoption and
  operational quality.

**Problems it solves.**
- Establishes a single source of truth for telemetry formatting, unlocking cross-team tooling
  reuse.
- Threads correlation IDs through asynchronous code paths, making distributed traces debuggable
  without bespoke instrumentation.
- Ensures every module can emit structured metrics and logs that satisfy audit trails and
  regulatory disclosure requirements.

---
By grounding module responsibilities in audited code paths and repeatable interfaces, the
GeoSync platform enables teams to scale research, execution, and governance activities with
confidence. Use this reference as the canonical baseline when scoping new integrations,
performing readiness reviews, or onboarding stakeholders into the system.
