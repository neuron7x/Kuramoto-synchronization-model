# Incident Playbooks

These playbooks codify our response to the highest-impact production incidents
for GeoSync: execution lag, rejected orders, and data gaps. Each scenario
includes telemetry hooks, mitigation steps, and on-call simulation drills.

## Execution Lag

**Symptoms**: Order acknowledgements exceed SLO (`p95` > 250 ms) or monitoring
alerts `execution_latency_high` fire.

**Immediate Actions**

1. **Stabilise pipeline** – Throttle strategy fan-out to 50% using the runtime
   circuit breaker.
2. **Inspect queues** – Check Redis queue depth (`orders_queue_depth`) and
   Kafka lag. Drain oldest partitions first.
3. **Fail over** – If broker adapter CPU > 80% or GC thrashing observed, route
   orders to the warm standby region.
4. **Communicate** – Post status update to `#inc-trading` and status page within
   10 minutes.

**Diagnostics Checklist**

- [ ] Compare recent deployments to determine potential regressions.
- [ ] Review p99 latency vs. network RTT in Grafana to spot exchange-side
      degradation.
- [ ] Capture flamegraph using `py-spy record -d 30` on the execution worker.

**Mitigations**

- Apply autoscaling rule override (`execution.autoscale boost=2x`).
- Temporarily disable optional risk calculations (Greeks, VaR) to free CPU.
- Increase client retry backoff to reduce pressure on the broker gateway.

**Postmortem Inputs**

- Export Prometheus query snapshots and attach CLI artifact hashes.
- Document whether latency breached SLO error budget (see SLO policy below).

## Rejected Orders

**Symptoms**: Rejection ratio > 0.5% over rolling 5 minutes, or exchange returns
`REJECTED`/`INVALID` statuses unexpectedly.

**Immediate Actions**

1. Flip the strategy guardrail toggle `strategy.reject_guard=true` to pause new
   submissions.
2. Page compliance if rejection reason indicates regulatory filters.
3. Run `geosync-cli exec --output jsonl` to inspect the latest signal for
   out-of-bound sizes or throttles.
4. Audit recent risk configuration changes (`configs/risk/allocations.yaml`).

**Diagnostics Checklist**

- [ ] Sample rejected FIX messages; verify timestamps and order IDs.
- [ ] Validate portfolio limits against the risk service (check audit logs).
- [ ] Cross-check broker API status pages for outages.

**Mitigations**

- Reduce order size multiplier until rejection rate drops <0.1%.
- Reset session keys or rotate API credentials if authentication failures are
  detected.
- Switch to passive order template if aggressive order types are blocked.

**Postmortem Inputs**

- Catalogue the rejection reasons grouped by exchange and symbol.
- Record time-to-detect, time-to-mitigate, and any missed alerts.

## Data Gaps

**Symptoms**: Missing ticks detected by backfill validator, data freshness lag
> 1.5 s, or `geosync_market_data_gaps_total` increments unexpectedly.

**Immediate Actions**

1. Execute `geosync-cli ingest --output jsonl` on the affected feed to confirm
   the most recent artifact checksum.
2. Fail over to redundant feed handlers or cached snapshots.
3. Notify quantitative leads to pause model retraining if gaps exceed thresholds.

**Diagnostics Checklist**

- [ ] Review ingestion job logs for upstream HTTP 429/500 responses.
- [ ] Inspect object storage manifests to confirm file counts and sizes.
- [ ] Validate sequence numbers to isolate the missing window.

**Mitigations**

- Trigger backfill job with seed configuration stored in
  `configs/seeds/<feed>.yaml`.
- Enable tolerance mode in downstream pipelines to forward-fill within safe
  bounds.
- Escalate to data vendors if multiple regions exhibit concurrent gaps.

**Postmortem Inputs**

- Attach data lineage (catalog entries, hashes) and gap duration metrics.
- Record which alerts fired and which playbooks were executed.

## On-Call Simulation Drills

- **Monthly game day** – Alternate between execution lag and data gap scenarios.
  Replay production traffic via the backtest simulator and require responders to
  use the CLI logs and hashes for verification.
- **Quarterly compliance drill** – Simulate mass order rejections and ensure
  communication templates are updated.
- **Runbook verification** – After each drill, update this document with gaps
  discovered during execution.

Tracking incident rehearsal outcomes alongside production metrics keeps on-call
engineers sharp and ensures every critical scenario has a rehearsed response.
