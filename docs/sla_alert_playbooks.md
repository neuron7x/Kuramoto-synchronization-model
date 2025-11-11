# SLA and Alert Playbooks

This catalogue links each production alert to the SLA it protects, the
monitoring queries that raise it, and the operational response pattern. The
playbooks align with the telemetry returned by the production dashboard endpoint
(`/api/v1/dashboard/production`).

## Latency and Availability

| Alert ID | Trigger Source | SLA / Target | Response Owner | Playbook |
| --- | --- | --- | --- | --- |
| `cb-half-open`, `cb-open` | Prometheus alert `TradePulseSignalToFillLatency` and circuit breaker telemetry | p95 signal-to-fill latency ≤ 650 ms (`observability/slo_policies.json`) | Execution engineer (primary), SRE (secondary) | 1. Confirm circuit breaker reason via dashboard.<br>2. Run [`docs/incident_playbooks.md#execution-lag`](incident_playbooks.md#execution-lag).<br>3. Capture Grafana panel snapshots and attach to incident ticket. |
| `kill-switch-drill`, `kill-switch-engaged` | Kill switch events emitted by `execution.risk.RiskManager` | Platform availability ≥ 99.5% | Duty officer | 1. Verify whether the switch was part of a scheduled drill.<br>2. If unscheduled, escalate to production lead, freeze deployments, and follow [`docs/incident_response_lifecycle.md`](incident_response_lifecycle.md). |
| `api-latency-burn` | Prometheus burn-rate alert for `tradepulse-api-latency` | HTTP error budget (1.5% over 5m) | API on-call | 1. Page API on-call, inform communications channel `#status-tradepulse`.<br>2. Enable rate limiting overrides if required.<br>3. Reference mitigation steps in [`docs/incident_playbooks.md#execution-lag`](incident_playbooks.md#execution-lag). |

## Data Quality and Ingestion

| Alert ID | Trigger Source | SLA / Target | Response Owner | Playbook |
| --- | --- | --- | --- | --- |
| `ingestion-freshness` | `TradePulseDataFreshness` Prometheus alert | Ingestion lag < 5 minutes | Data engineering | 1. Inspect ingestion job logs (dashboard `orders.rejectionRate` often spikes during lag).<br>2. Launch [`docs/runbook_data_incident.md`](runbook_data_incident.md).<br>3. Communicate expected recovery time to quantitative leads. |
| `ingestion-failure` | `TradePulseDataIngestionFailures` Prometheus alert | Ingestion success rate ≥ 99% | Data engineering | 1. Use `tradepulse-cli ingest --output jsonl` to reproduce failure.<br>2. If multiple venues affected, fail over to redundant feed handlers.<br>3. File incident ticket referencing `reports/incidents/` templates. |

## Order Health

| Alert ID | Trigger Source | SLA / Target | Response Owner | Playbook |
| --- | --- | --- | --- | --- |
| `order-rejection-rate` | Derived from dashboard metric `orders.rejectionRate` > 0.5% | Rejection ratio ≤ 0.5% (5 minute window) | Execution operations | 1. Enable `strategy.reject_guard` using remote control API.<br>2. Audit rejection reasons (`tradepulse-cli exec --output jsonl`).<br>3. Follow mitigation checklist in [`docs/incident_playbooks.md#rejected-orders`](incident_playbooks.md#rejected-orders). |
| `circuit-trips` | Dashboard metric `orders.circuitTrips` > 0 in consecutive windows | Circuit trip frequency ≤ 2 per hour | SRE with compliance on standby | 1. Review circuit breaker timeline and cooldown on dashboard.<br>2. Validate guardrail configuration from `configs/risk.yaml`.<br>3. If trips persist, escalate using [`docs/incident_response_lifecycle.md`](incident_response_lifecycle.md). |

## Using the Playbooks

1. **Acknowledge** the alert within five minutes in the relevant channel.
2. **Consult** this document to identify the SLA at risk and the owning team.
3. **Execute** the linked runbook, ensuring all steps are logged in the incident
   ticket.
4. **Close** the alert only after verifying the dashboard metrics have returned
   within their guardrails.

Maintaining the linkage between alerts, SLAs, and response steps ensures the
error budget reports in `observability/slo_policies.json` reflect operational
reality and helps the platform stay audit-ready.
