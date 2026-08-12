# Reliability Targets, SLOs, and Escalation Policy

This playbook aligns GeoSync engineering and operations teams on the
service-level commitments we communicate to stakeholders. It converts product
expectations into actionable SLOs with explicit error budgets, alerting rules,
and escalation paths so reliability work can be prioritised alongside feature
work.

## Scope and Ownership

| Domain | Services | Primary Owners | Supporting Teams |
| ------ | -------- | -------------- | ---------------- |
| Client API | REST/GraphQL edge, authentication, request fan-out | Execution Platform | Infrastructure, SRE |
| Market Data | Real-time ingestion, historical snapshots, feature stores | Data Platform | Infrastructure |
| Strategy Runtime | Signal evaluation, backtest coordinator, portfolio engine | Quant Engineering | SRE |
| Order Execution | Broker adapters, risk guards, position reconciliation | Execution Platform | Compliance, Infrastructure |

Each domain lead is accountable for SLO definitions, observing error budget
consumption, and initiating corrective actions. SRE facilitates the review
cadence and provides tooling support.

## SLA Commitments

GeoSync publishes the following externally visible SLAs. SLOs must be set
with sufficient safety margin to guarantee the SLA when measured over a rolling
90-day window.

| Capability | SLA Metric | Customer Commitment |
| ---------- | ---------- | ------------------- |
| Client API availability | Successful request ratio | ≥ 99.5% |
| Strategy order latency | Time from order submit to broker acknowledgement | ≤ 400 ms for 95% of orders |
| Market data freshness | Delay between exchange event and availability via API | ≤ 3 seconds 99% of the time |
| Model inference availability | Successful inference ratio | ≥ 99.5% |
| Model inference latency | p95 time to return model scores | ≤ 200 ms |

Breaching an SLA triggers incident review with product and customer success and
may require service credits per contractual terms.

## Service-Level Objectives

Internal SLOs are tuned tighter than SLAs to preserve buffer. Objectives are
tracked weekly and trended quarterly.

| Service | SLI Definition | Target | Measurement Window |
| ------- | -------------- | ------ | ------------------ |
| Client API | Ratio of 2xx/3xx responses to total requests, excluding 4xx | 99.9% availability | Rolling 30 days |
| Client API latency | p95 end-to-end latency for `/orders` and `/positions` | ≤ 250 ms | 5-minute sliding windows |
| Strategy runtime | Successful job completions / attempted jobs | 99.7% | Rolling 7 days |
| Strategy runtime latency | p99 time to produce decision from signal batch | ≤ 120 ms | 1-hour buckets |
| Order execution | Orders confirmed within broker SLA / total orders | 99.9% | Rolling 30 days |
| Market data freshness | Percentage of ticks arriving < 1.5 s from event time | 99.8% | Rolling 24 hours |
| Data pipeline accuracy | Jobs with parity checks passing / total jobs | 99.95% | Rolling 30 days |
| Trade pipeline latency | p95 signal → order → ack duration | ≤ 400 ms | 5-minute sliding windows |
| Trade pipeline reliability | p99 signal → order → fill duration | ≤ 650 ms | 5-minute sliding windows |
| Model inference availability | Successful inference ratio / total requests | 99.8% | Rolling 30 days |
| Model inference latency | p95 inference time across online models | ≤ 150 ms | 5-minute sliding windows |

Targets assume at least 1,000 valid events per window; otherwise the period is
flagged for manual review.

### Streaming KPIs

| Capability | SLI Definition | Target | Measurement Notes |
| ---------- | -------------- | ------ | ----------------- |
| Ingestion latency | Median time from exchange event to ingestion artifact registration | ≤ 45 s | Derived from catalog timestamps and upstream feed events. |
| Signal freshness | Percentage of live signals generated within 500 ms of market tick | ≥ 99.2% | Calculated via CEP pipeline telemetry. |
| Order acknowledgements | Ratio of orders acked < 250 ms / total orders | ≥ 99.5% | Split by venue; tracked via execution metrics. |
| Fill ratio | Executed quantity / submitted quantity (per venue) | ≥ 92% | Evaluate over rolling 60 minutes with volume weighting. |

SLIs feed Grafana dashboards and the automated quality gates. Any regression
greater than 2% against target triggers an error-budget burn review.

### Error Budget Policy

Error budgets are derived as `(1 - SLO target)` per window. The following guard
rails apply:

- **Green (< 25% consumed)** – Continue regular releases. Document regression
  tests relevant to observed risks.
- **Yellow (25–75% consumed)** – Require SRE sign-off for deploys touching the
  affected service. Increase sampling on synthetic probes and ensure alert run
  books are updated.
- **Red (> 75% consumed)** – Freeze non-critical deploys. Run a game-day or
  chaos exercise targeting the affected component within two weeks. Schedule a
  postmortem review with engineering and product leadership.

Error budget burn rates are evaluated hourly using Grafana burn-rate panels and
Prometheus recording rules. Alerts fire when projected exhaustion is under 72
hours for Red services or 7 days for Yellow services.

**Service-Specific Policies**

- **Ingestion latency** – When burn rate exceeds 2×, pause non-essential ETL
  jobs and require data team sign-off for schema migrations.
- **Signal freshness** – Enable degraded-mode execution (wider throttles) after
  25% budget consumption. Require strategy owners to provide mitigation plans.
- **Order ACK latency** – Divert new releases away from affected brokers at
  50% consumption; escalate to broker account managers.
- **Fill ratio** – Enforce tighter risk caps (−20%) and trigger liquidity
  provider outreach once consumption exceeds 60%.
- **Model inference latency** – Enable cache-first scoring and shed shadow
  traffic when burn exceeds 25%. Trigger rollback evaluation at 50%.
- **Model inference availability** – Freeze promotions immediately and escalate
  to MLOps for potential rollback and data drift triage.

## Reliability and Chaos Scenarios

Emergency drills must validate both reliability failures and chaos-style fault
injection. Use these scenarios to keep response paths fresh and aligned with
observability guardrails.

| Scenario | Trigger | Expected Response | Reference |
| -------- | ------- | ----------------- | --------- |
| Inference latency spike | p95 inference latency > 150 ms for 10 minutes | Scale inference, enable cache-first mode, evaluate rollback | [`runbook_latency_degradation.md`](runbook_latency_degradation.md) |
| Model quality regression | Quality degradation events > threshold | Pause promotions, run drift response, prepare rollback | [`runbook_data_drift_response.md`](runbook_data_drift_response.md) |
| Exchange latency chaos | Injected network delay ≥ 2s | Degraded mode, throttle orders, verify guardrails | [`chaos_cost_controls.md`](chaos_cost_controls.md) |
| Data feed gap | Missing or stale ingestion | Backfill and failover to backup feed | [`runbook_data_incident.md`](runbook_data_incident.md) |

Reliability scenarios must also map to automated tests in
[`docs/RELIABILITY_SCENARIOS.md`](RELIABILITY_SCENARIOS.md) and to chaos drills
defined in [`docs/chaos_cost_controls.md`](chaos_cost_controls.md).

## Alerting and Escalation

### Severity Ladder

| Severity | Trigger Examples | Response Expectation |
| -------- | ---------------- | -------------------- |
| SEV-1 | SLA breach in progress, sustained 30-min outage, data corruption | Page on-call immediately, incident commander within 5 minutes, notify leadership within 15 minutes |
| SEV-2 | SLO violation projected within 24 hours, partial feature outage | Page on-call within 15 minutes, engage domain owner, customer updates every hour |
| SEV-3 | Degraded performance without customer impact, tooling failure | Create Jira ticket, respond in business hours, update status weekly |

### Escalation Flow

1. **Detection** – Prometheus alerts, synthetic probes, or support cases detect
   an issue and route to PagerDuty (`GeoSync/SRE` schedule).
2. **On-call response** – On-call acknowledges within 5 minutes (SEV-1/2) or the
   next business hour (SEV-3). They open an incident channel (`#inc-YYYYMMDD`) and
   start an incident log.
3. **Escalation** – If unresolved within 15 minutes (SEV-1) or 60 minutes
   (SEV-2), page the domain engineering manager. Persistent degradation triggers
   escalation to VP Engineering and Product lead.
4. **Communications** – Customer success posts updates to the status page every
   30 minutes for SEV-1 and hourly for SEV-2. Post-incident report is due within
   48 hours of resolution.

## Governance and Review Cadence

- **Weekly** – Review error budget dashboard in SRE sync, assign owners to
  investigate burn trends.
- **Monthly** – Domain leads refresh SLO definitions and validate alert
  thresholds. Update this document with changes and circulate meeting notes.
- **Quarterly** – Leadership reviews SLA adherence, approves budget for
  reliability initiatives, and signs off on any SLA changes.

Change proposals to SLO targets or escalation rules must be tracked via RFC with
sign-off from SRE lead, affected domain owner, and product counterpart.

## Unified Timekeeping Requirements

- **Clock synchronisation** – All production hosts run `chronyd` pointed at the
  GeoSync Stratum-1 pool (`time.geosync.net`) with fallback to regional NTP
  peers. Co-located execution racks enable PTP (IEEE 1588) and expose hardware
  timestamps to NICs so trade plant remains aligned within ±5 μs.
- **Configuration management** – The `infra.time-sync` automation role enforces
  max-offset (50 ms), polling cadence, and fallback peers. CI images fail
  promotion when `chronyc tracking` reports drift beyond the threshold.
- **Monotonic clocks** – Runtime services measure durations via monotonic clock
  APIs (`time.monotonic_ns()` in Python, `CLOCK_MONOTONIC_RAW` in Go) to avoid
  retrograde time jumps when NTP/PTP corrections occur. Wall-clock timestamps are
  attached only at ingestion/egress boundaries for audit trails.

Any host exceeding the drift limits is automatically quarantined by the
deployment orchestrator, and SRE receives a SEV-2 alert to remediate or rotate
the instance.
