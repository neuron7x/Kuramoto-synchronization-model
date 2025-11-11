# Production Dashboard Operations Guide

The production dashboard gives on-call operators a single view of TradePulse's
core trading safety controls. It complements the Grafana boards and Prometheus
alerts by presenting actionable telemetry in one place, backed by the same
sources used by automated guardrails.

## Data Sources

The API endpoint `/api/v1/dashboard/production` hydrates the dashboard with a
curated snapshot assembled by `observability.dashboard.production`:

- **Kill switch** state and recent transitions (`execution.risk.RiskManager`).
- **Circuit breaker** status from the resilience layer.
- **Gross exposure** and **drawdown** trajectories sourced from the risk audit
  trail and persisted telemetry snapshots.
- **Order health** statistics (open orders, rejection rate, circuit trips) used
  to detect execution pressure early.
- **Alerts** synthesised from Prometheus and operational runbooks, aligned with
  SLA policies.

The endpoint returns JSON that mirrors the UI contract in
`ui/dashboard/src/views/monitoring.js`. Each payload includes current metrics,
trend deltas, and the raw series required to render charts or export the data to
other tools. Consumers can safely cache responses for short intervals because
the API advertises cache-control headers matching the TTL used by the
`ProductionTelemetryStore`.

## Operational Workflow

1. **Triaging alerts** – When the dashboard surfaces a `warning` or `critical`
   alert, link directly to the corresponding playbook in
   [`docs/sla_alert_playbooks.md`](sla_alert_playbooks.md).
2. **Kill switch decisions** – The `previous` field contains the last recorded
   state change, allowing responders to verify whether the switch was part of a
   drill or an ongoing mitigation. Cross-check with incident tickets before
   resetting.
3. **Circuit breaker** – The `cooldownSeconds` field shows how long the breaker
   will remain open before attempting to re-close. Operators should wait for the
   cooldown to expire and confirm latency has normalised before forcing a reset.
4. **Exposure and drawdown trends** – Positive deltas indicate increasing gross
   exposure or improving drawdown. Large negative swings should trigger a review
   of recent deployments or strategy parameter changes.
5. **Order health** – Rising rejection rates or frequent circuit trips require
   coordination with the compliance lead and execution engineers per the
   incident lifecycle documented in [`docs/incident_response_lifecycle.md`](incident_response_lifecycle.md).

## API Contract

The endpoint returns the following top-level structure:

```json
{
  "environment": "prod",
  "currency": "USD",
  "controls": {
    "killSwitch": { "enabled": false, "changedAt": 1739995800000 },
    "circuitBreaker": { "state": "closed", "triggeredAt": 1739994000000 }
  },
  "metrics": {
    "grossExposure": { "value": 1287500.0, "limit": 1500000.0, "trend": 107500.0 },
    "drawdown": { "value": -0.033, "limit": -0.08, "trend": -0.002 },
    "orders": { "open": 133, "rejectionRate": 0.0016, "circuitTrips": 0 },
    "pnl": { "realized": 12500.5, "unrealized": -320.75, "drawdown": 0.031 }
  },
  "timeSeries": {
    "exposure": [ { "timestamp": 1739993400000, "value": 1255000.0 } ],
    "drawdown": [ { "timestamp": 1739993400000, "value": -0.036 } ]
  },
  "alerts": [ { "id": "cb-half-open", "severity": "warning", "message": "Circuit breaker entered half-open" } ]
}
```

Timestamps are expressed in Unix milliseconds. Clients should treat missing
values as unavailable data rather than zero and rely on the trend fields for
headline movement instead of recomputing deltas locally.

## Automation Hooks

- **Inspectors** – The FastAPI debug inspector now exposes
  `production_dashboard` so operators can view snapshot metadata without hitting
  the live endpoint.
- **Runbook links** – Alerts returned by the API include stable IDs. The UI maps
  these to the corresponding documents under `docs/` to ensure every alert is
  backed by a concrete action plan.
- **Snapshots** – The default data set is stored in
  `reports/telemetry/production_dashboard_snapshot.json`. Environments can
  override the path via `TRADEPULSE_BACKEND_PRODUCTION_DASHBOARD_SNAPSHOT` to
  hydrate the dashboard with environment-specific data during bootstrapping.

Adhering to this contract keeps the dashboard authoritative for live operations
and allows automation to ingest the same telemetry surfaced to humans.
