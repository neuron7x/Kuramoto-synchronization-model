# TradePulse Documentation Portal

Welcome to the TradePulse knowledge base. This site organises the core
concepts, APIs, and operational guides required to build, validate, and run
quantitative trading strategies with the platform. Each section links to a
focused document so contributors can quickly find the details they need.

---

## Architecture Overview

- **High-level system design** – see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
  for component boundaries, data flow, and deployment topologies.
- **FPM-A phase/regime model** – the methodology that powers TradePulse’s
  adaptive agents is described in [`docs/FPM-A.md`](FPM-A.md), including phase
  catalogues, orchestration contracts, and reproducible benchmarks.
- **Monitoring & operations** – instrumentation, alerting, and dashboard
  recipes live in [`docs/monitoring.md`](monitoring.md).
- **Chaos & cost governance** – container stress campaigns, FinOps controls,
  and research workload guardrails are captured in
  [`docs/chaos_cost_controls.md`](chaos_cost_controls.md).
- **Risk, signals, and observability controls** – consolidated guardrails for
  portfolio risk, model governance, and Prometheus coverage are in
  [`docs/risk_ml_observability.md`](risk_ml_observability.md).
- **Керування чергами та backpressure** – політики контролю навантаження,
  sizing черг і runbook'и описані у
  [`docs/queue_and_backpressure.md`](queue_and_backpressure.md).
- **Serving resilience blueprint** – systematic plan covering critical paths, queueing, caching,
  failover, and reliability primitives for the inference API in
  [`docs/architecture/serving_resilience.md`](architecture/serving_resilience.md).
- **Reliability & SRE** – SLA commitments, SLOs, error budgets, and escalation
  policy are outlined in [`docs/reliability.md`](reliability.md).

---

## Core Capabilities

| Topic | What you will learn | Primary References |
| ----- | ------------------- | ------------------ |
| Indicators | Kuramoto phase sync, entropy, Hurst exponent, Ricci curvature, and how to assemble feature blocks. | [`docs/indicators.md`](indicators.md), [`core/indicators`](../core/indicators) |
| Agent System | Strategy lifecycle, mutation/repair flow, instability detection, and multi-armed bandits. | [`docs/agent.md`](agent.md), [`core/agent`](../core/agent) |
| Backtesting | Deterministic walk-forward engine, signal requirements, and diagnostics. | [`docs/backtest.md`](backtest.md), [`backtest/engine.py`](../backtest/engine.py) |
| Execution & Risk | Order sizing utilities, portfolio heat checks, and integration touchpoints. | [`docs/execution.md`](execution.md), [`execution`](../execution) |
| Execution Simulation | Latency, queueing, halts, and time-in-force handling for research-grade fills. | [`docs/backtest_execution_simulation.md`](backtest_execution_simulation.md), [`backtest/execution_simulation.py`](../backtest/execution_simulation.py) |
| Stress & Portfolio Resilience | Historic scenario replays, chaos exercises, and capital allocation guardrails. | [`docs/stress_playbooks.md`](stress_playbooks.md) |
| Chaos & Cost Governance | Container stress testing, budget tagging, and cost-aware research workflows. | [`docs/chaos_cost_controls.md`](chaos_cost_controls.md) |
| CLI & Interfaces | Automations for analysis/backtest/live commands and scripting entrypoints. | [`interfaces/cli.py`](../interfaces/cli.py) |

---

## Getting Started

1. **Follow the [Quick Start Guide](quickstart.md)** to install dependencies,
   run the CLI, and execute your first analysis.
2. **Study the [Developer Scenarios](scenarios.md)** for task-oriented
   tutorials that cover indicator creation, backtests, live ingestion, and
   strategy optimisation.
3. **Explore [Extending TradePulse](extending.md)** when you are ready to add
   custom indicators, strategies, or integrations.

---

## Strategic Direction

- Review the [TradePulse Roadmap](roadmap.md) for the current development map and
  quarterly priorities.
- Cross-reference the [Improvement Plan](improvement_plan.md) for detailed
  success criteria and implementation guidance.
- Align governance and compliance using the
  [Governance and Data Controls](governance.md) playbook covering RBAC, data
  contracts, privacy, and catalog management.
- Align on safeguards using the [Risk, Signals, and Observability Control
  Blueprint](risk_ml_observability.md) when planning high-impact releases.

---

## Operational Excellence

- Consult the [Operational Excellence Handbook](operational_handbook.md) for a
  single index of runbooks, performance budgets, data lake procedures, and
  governance guardrails.
- Execute cross-region recovery using the
  [Disaster Recovery & Multi-Region Failover Runbook](runbook_disaster_recovery.md)
  to uphold RPO/RTO commitments when a site becomes unavailable.
- Enforce automation and exception handling with the
  [Quality Gates and Automated Governance guide](quality_gates.md).
- Rehearse incident response with the dedicated
  [Incident Playbooks](incident_playbooks.md) and runbooks for data integrity
  and live-trading operations.
- Harden key management workflows with the
  [Secret Rotation Runbook](runbook_secret_rotation.md) and
  [Secret Leak Response Runbook](runbook_secret_leak.md).

---

## Contribution Workflow

- Adhere to the testing instructions in [`TESTING.md`](../TESTING.md) and the
  quality checklist documented in [`reports/release_readiness.md`](../reports/release_readiness.md).
- For production cutovers, complete the
  [`Production Cutover Readiness Checklist`](../reports/prod_cutover_readiness_checklist.md)
  alongside the go/no-go review.
- Keep documentation in sync with the public APIs exposed by modules such as
  [`core/agent/strategy.py`](../core/agent/strategy.py) and
  [`execution/order.py`](../execution/order.py).
- When adding major features, update this index so the navigation reflects the
  newest capabilities.
- Apply the practices in the [Technical Debt Management Playbook](technical-debt.md)
  to sustain healthy engineering velocity while avoiding unplanned outages.
- Use the [Quality DoR/DoD checklist](quality-dor-dod.md) to enforce clear entry
  and exit criteria before pulling or closing quality-focused work.
- Align with the [Documentation Governance and Quality Framework](documentation_governance.md)
  when planning, reviewing, or auditing knowledge base changes to keep content
  accurate and discoverable.

---

**Last updated:** 2025-10-19
