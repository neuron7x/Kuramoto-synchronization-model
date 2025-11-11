# SLA/ALERT Response Playbooks

This document provides comprehensive response procedures for every alert defined in TradePulse, mapping alerts to SLAs, escalation paths, and resolution playbooks. Use this as the primary reference when alerts fire in production.

## Quick Reference Matrix

| Alert Name | Severity | SLA Impact | Response Time | Playbook Section |
|------------|----------|------------|---------------|------------------|
| TradePulseOrderErrorRate | Critical | High | < 5 min | [Order Error Rate](#order-error-rate-alert) |
| TradePulseOrderLatency | Warning | Medium | < 15 min | [Order Latency](#order-latency-alert) |
| TradePulseOrderAckLatency | Warning | Medium | < 15 min | [Order Acknowledgement Latency](#order-acknowledgement-latency-alert) |
| TradePulseSignalToFillLatency | Critical | High | < 5 min | [Signal to Fill Latency](#signal-to-fill-latency-alert) |
| TradePulseDataIngestionFailures | Critical | High | < 5 min | [Data Ingestion Failures](#data-ingestion-failures-alert) |
| TradePulseDataFreshness | Warning | Medium | < 15 min | [Data Freshness](#data-freshness-alert) |
| TradePulseVenueDivergence | Critical | High | < 5 min | [Venue Divergence](#venue-divergence-alert) |
| TradePulseFeatureStoreLag | Warning | Medium | < 15 min | [Feature Store Lag](#feature-store-lag-alert) |
| TradePulseReconciliationDrift | Critical | High | < 10 min | [Reconciliation Drift](#reconciliation-drift-alert) |
| TradePulseBacktestFailures | Warning | Low | < 30 min | [Backtest Failures](#backtest-failures-alert) |
| TradePulseOptimizationSlow | Info | Low | < 1 hour | [Optimization Slow](#optimization-slow-alert) |
| TradePulseCriticalIncidentOpen | Critical | High | Immediate | [Critical Incident Open](#critical-incident-open-alert) |
| TradePulseIncidentAckSLA | Warning | Medium | < 10 min | [Incident Acknowledgement SLA](#incident-acknowledgement-sla-alert) |
| TradePulseLifecycleCheckpointBlocked | Critical | High | < 5 min | [Lifecycle Checkpoint Blocked](#lifecycle-checkpoint-blocked-alert) |
| TradePulseRunbookFailures | Warning | Medium | < 15 min | [Runbook Execution Failures](#runbook-execution-failures-alert) |

## SLA Definitions

### API Latency SLA
- **Target**: 99% of requests < 350ms
- **Error Budget**: 1.5% error rate over 30 days
- **Measurement**: 5-minute rolling window
- **Burn Rate Thresholds**:
  - Rapid burn: 14.4x over 5 minutes → Page on-call immediately
  - Slow burn: 6.0x over 1 hour → Create incident ticket

### Ingestion Availability SLA
- **Target**: 99% successful ingestion jobs
- **Error Budget**: 1% failure rate over 30 days
- **Measurement**: 10-minute rolling window
- **Burn Rate Thresholds**:
  - Rapid burn: 12.0x over 10 minutes → Page on-call immediately
  - Slow burn: 4.0x over 2 hours → Create incident ticket

### Signal Pipeline SLA
- **Target**: P95 latency < 250ms
- **Error Budget**: 2% error rate over 30 days
- **Measurement**: 15-minute rolling window
- **Burn Rate Thresholds**:
  - Rapid burn: 8.0x over 15 minutes → Page on-call immediately
  - Slow burn: 3.0x over 6 hours → Create incident ticket

### Market Data Delivery SLA
- **Target**: Venue freshness skew < 45 seconds between primary and secondary feeds
- **Error Budget**: 1% of intervals breaching target over 30 days
- **Measurement**: 1-minute rolling window using `tradepulse_market_data_freshness_seconds`
- **Burn Rate Thresholds**:
  - Rapid burn: Max freshness > 90 seconds for 3 consecutive minutes → Page data steward and SRE on-call
  - Slow burn: Median freshness > 60 seconds for 20 minutes → Create incident and initiate venue drill

### Feature Store Synchronisation SLA
- **Target**: Derived feature batches land within 4 minutes of raw ingestion
- **Error Budget**: 3% of batches exceeding 4 minutes over 30 days
- **Measurement**: 5-minute rolling window using `tradepulse_feature_store_sync_delay_seconds`
- **Burn Rate Thresholds**:
  - Rapid burn: P90 delay > 8 minutes for 10 minutes → Page platform on-call
  - Slow burn: P75 delay > 6 minutes for 30 minutes → Notify data engineering lead

### Portfolio Reconciliation SLA
- **Target**: Absolute drift between broker and internal positions < 0.35%
- **Error Budget**: 0.5% of reconciliation windows breaching threshold over 30 days
- **Measurement**: 15-minute rolling window using `tradepulse_position_drift_ratio`
- **Burn Rate Thresholds**:
  - Rapid burn: Drift > 1% for 5 minutes → Trigger reconciliation drill and page risk officer
  - Slow burn: Drift > 0.6% for 45 minutes → Escalate to duty manager and schedule near-term retro

### Incident Acknowledgement SLA
- **Target**: Median acknowledgement < 5 minutes
- **Error Budget**: 2% of incidents exceeding 5 minutes over 30 days
- **Measurement**: 5-minute rolling window on `tradepulse_incident_ack_latency_seconds` histogram
- **Burn Rate Thresholds**:
  - Rapid burn: Median acknowledgement > 5 minutes for 10 minutes → Page platform on-call
  - Slow burn: Median acknowledgement > 4 minutes for 1 hour → Escalate to incident commander

### Incident Resolution SLA
- **Target**: Median resolution < 30 minutes for Sev1/Sev2 incidents
- **Error Budget**: 5% of incidents exceeding 30 minutes over 30 days
- **Measurement**: 15-minute rolling window on `tradepulse_incident_resolution_latency_seconds` histogram
- **Burn Rate Thresholds**:
  - Rapid burn: Median resolution > 45 minutes for 15 minutes → Page duty manager
  - Slow burn: Median resolution > 35 minutes for 2 hours → Trigger problem management review

---

## Alert Response Procedures

### Order Error Rate Alert

**Alert Definition**: More than 5% of orders failed in the last 5 minutes

**SLA Impact**: Direct impact on API Latency SLA error budget

**Immediate Response (< 5 minutes)**:
1. **Acknowledge** the alert in PagerDuty
2. **Check** the Production Operations Dashboard for context
3. **Open** incident channel: `#inc-trading-<timestamp>`
4. **Execute** initial triage:
   ```bash
   # Check recent order errors
   tradepulse-cli orders list --status error --since 5m --output jsonl | jq '.rejection_reason' | sort | uniq -c
   
   # Check broker adapter health
   tradepulse-cli health check --service broker-adapter
   ```

**Diagnostics (5-15 minutes)**:
- Review recent deployments in the last hour
- Check broker API status pages for outages
- Inspect authentication/credential expiry
- Validate risk limits haven't been breached
- Review FIX message logs for rejection codes

**Mitigation Steps**:
1. **If credential issue**: Rotate API keys using [`docs/runbook_secret_rotation.md`](runbook_secret_rotation.md)
2. **If broker outage**: Fail over to backup broker or halt trading
3. **If risk limit breach**: Adjust limits in `configs/risk/allocations.yaml` after approval
4. **If deployment regression**: Rollback using blue/green procedure

**Communication**:
- **Internal**: Post status to `#inc-trading` every 15 minutes
- **External**: Update status page if customer-facing
- **Escalation**: Page Risk Officer if rejection rate > 10% for 10+ minutes

**Resolution**:
- Verify error rate < 0.5% for 10 consecutive minutes
- Document root cause in incident report
- Update error budget tracking

**Related Documents**:
- [`docs/incident_playbooks.md`](incident_playbooks.md) - Rejected Orders section
- [`docs/runbook_live_trading.md`](runbook_live_trading.md)

---

### Order Latency Alert

**Alert Definition**: P95 order placement latency exceeded 2 seconds for 10 minutes

**SLA Impact**: Warning indicator for API Latency SLA

**Immediate Response (< 15 minutes)**:
1. **Acknowledge** alert in PagerDuty
2. **Check** Production Operations Dashboard latency panel
3. **Assess** if this is trending toward critical threshold (350ms SLA)
4. **Execute** quick diagnostics:
   ```bash
   # Check current latency distribution
   tradepulse-cli metrics query 'histogram_quantile(0.95, tradepulse_order_placement_duration_seconds_bucket[5m])'
   
   # Check queue depths
   tradepulse-cli metrics query 'tradepulse_queue_depth{queue="orders"}'
   ```

**Diagnostics (15-30 minutes)**:
- Review execution worker CPU/memory utilization
- Check Redis/Kafka queue lag
- Inspect network latency to broker
- Review concurrent strategy count

**Mitigation Steps**:
1. **If queue backup**: Drain queues by increasing worker count
2. **If CPU saturation**: Apply autoscaling boost or disable non-critical features
3. **If network degradation**: Check broker connectivity, consider regional failover
4. **If strategy overload**: Throttle strategy fan-out to 50%

**Communication**:
- Post advisory to `#trading-ops`
- No external communication unless approaching SLA breach

**Resolution**:
- Confirm P95 latency < 2s for 15 consecutive minutes
- Document mitigations applied
- Review for preventive actions

**Related Documents**:
- [`docs/incident_playbooks.md`](incident_playbooks.md) - Execution Lag section

---

### Order Acknowledgement Latency Alert

**Alert Definition**: P95 signal to acknowledgement latency exceeded 400ms for 5 minutes

**SLA Impact**: Contributes to overall Signal Pipeline SLA

**Immediate Response (< 15 minutes)**:
1. **Acknowledge** alert
2. **Check** signal processing pipeline health
3. **Review** broker acknowledgement response times

**Diagnostics**:
- Inspect order submission to broker latency
- Check broker adapter queue processing
- Review acknowledgement message parsing times
- Validate WebSocket connection health

**Mitigation Steps**:
1. **Increase** broker adapter worker threads
2. **Optimize** acknowledgement parsing if CPU-bound
3. **Fail over** to warm standby if broker-side latency
4. **Throttle** new signal generation if overload detected

**Communication**:
- Post to `#trading-ops` if sustained > 15 minutes
- Escalate to Execution Trader if exceeds 1s

**Resolution**:
- Verify P95 ack latency < 400ms for 10 minutes
- Update performance baselines if needed

---

### Signal to Fill Latency Alert

**Alert Definition**: P99 signal to fill latency exceeded 650ms for 5 minutes

**SLA Impact**: Critical impact on Signal Pipeline SLA

**Immediate Response (< 5 minutes)**:
1. **Page** on-call SRE immediately
2. **Open** critical incident channel
3. **Execute** emergency diagnostics:
   ```bash
   # Check end-to-end latency breakdown
   tradepulse-cli trace latency --metric signal_to_fill --window 5m
   
   # Check execution worker status
   tradepulse-cli health check --service execution-worker --verbose
   ```

**Diagnostics (5-10 minutes)**:
- Identify latency bottleneck (signal generation, order placement, broker fill)
- Check for network issues to broker
- Review execution worker GC pauses
- Validate fill message processing

**Mitigation Steps**:
1. **Critical Path**: If broker latency → Consider trading halt
2. **System Path**: If internal → Apply circuit breaker and boost resources
3. **Emergency**: If cannot resolve in 15 minutes → Initiate kill-switch preparation

**Communication**:
- **Immediate**: Post to `#inc-trading` within 5 minutes
- **Continuous**: Update every 10 minutes
- **Escalation**: Page Risk Officer and Trading Desk if > 1s latency

**Resolution**:
- Verify P99 latency < 650ms for 15 minutes
- Complete full postmortem within 48 hours
- Update latency budget if architecture changed

**Related Documents**:
- [`docs/incident_playbooks.md`](incident_playbooks.md) - Execution Lag section
- [`docs/runbook_kill_switch_failover.md`](runbook_kill_switch_failover.md)

---

### Data Ingestion Failures Alert

**Alert Definition**: At least one ingestion job reported errors in the last 10 minutes

**SLA Impact**: Critical impact on Ingestion Availability SLA

**Immediate Response (< 5 minutes)**:
1. **Acknowledge** alert
2. **Identify** failing ingestion jobs:
   ```bash
   # List recent failed ingestions
   tradepulse-cli ingest status --status error --since 10m
   
   # Check specific job logs
   tradepulse-cli logs ingestion-worker --level error --since 10m
   ```
3. **Assess** impact on downstream systems

**Diagnostics (5-15 minutes)**:
- Check upstream data provider status
- Review authentication/API key validity
- Inspect network connectivity to data sources
- Validate data format compatibility
- Check storage quotas and permissions

**Mitigation Steps**:
1. **If provider outage**: Fail over to backup data source
2. **If auth issue**: Rotate credentials
3. **If format change**: Apply data adapter fix or roll back
4. **If quota exceeded**: Clean up old data or request increase
5. **If network issue**: Check firewall rules and routing

**Communication**:
- Post to `#data-pipeline` immediately
- Notify quantitative leads if gaps exceed 5 minutes
- Update status page if customer-facing features affected

**Resolution**:
- Verify successful ingestion for 3 consecutive runs
- Backfill any data gaps using:
  ```bash
  tradepulse-cli ingest backfill --source <feed> --start <time> --end <time>
  ```
- Document gap duration and root cause

**Related Documents**:
- [`docs/runbook_data_incident.md`](runbook_data_incident.md)
- [`docs/incident_playbooks.md`](incident_playbooks.md) - Data Gaps section

---

### Data Freshness Alert

**Alert Definition**: Average ingestion lag exceeded five minutes

**SLA Impact**: Warning indicator for Ingestion Availability SLA

**Immediate Response (< 15 minutes)**:
1. **Check** current data lag:
   ```bash
   tradepulse-cli metrics query 'time() - tradepulse_data_last_ingestion_timestamp'
   ```
2. **Review** ingestion job performance
3. **Assess** if trending toward critical

**Diagnostics**:
- Check ingestion worker processing speed
- Review upstream API rate limits
- Inspect queue depths
- Validate data volume changes

**Mitigation Steps**:
1. **Scale** ingestion workers horizontally
2. **Optimize** data processing pipeline
3. **Request** rate limit increase from provider
4. **Enable** parallel ingestion if available

**Communication**:
- Post advisory to `#data-pipeline`
- Notify downstream consumers if lag > 10 minutes

**Resolution**:
- Verify data lag < 2 minutes for 15 minutes
- Tune ingestion parameters if needed

---

### Venue Divergence Alert

**Alert Definition**: Delta between primary and secondary venue mid-prices exceeds 15 bps for 2 minutes

**SLA Impact**: Consumes Market Data Delivery SLA error budget

**Immediate Response (< 5 minutes)**:
1. **Acknowledge** the alert and create incident stub `INC-VENUE-<timestamp>`
2. **Query** divergence metrics:

   ```bash
   tradepulse-cli metrics query 'tradepulse_market_data_divergence_bps{pair="BTC-USD"}'
   ```

3. **Check** network telemetry for packet loss towards the affected venue using the NOC portal

**Diagnostics (5-15 minutes)**:
- Review ticker parity via `tradepulse-cli market compare --venues primary,secondary --since 10m`
- Confirm price bands with broker reference feed
- Inspect ingestion logs under `observability/logs/ingestion/*.log`

**Mitigation Steps**:
1. Disable the drifting venue via the feature flag API (`ingestion.<venue>.enabled=false`)
2. Trigger the clean-room rebuild of the last 15 minutes of features
3. Re-route strategies configured for dual venue to backup venue using `tradepulse-cli strategy reroute`

**Communication**:
- Update `#inc-trading` every 10 minutes and include divergence graph
- Notify compliance if divergence persists > 30 minutes

**Resolution**:
- Divergence < 5 bps for 20 consecutive minutes across venues
- Data stewardship review logged in `reports/live/<date>/sla_incidents.md`

**Related Documents**:
- [`docs/OPERATIONS.md`](OPERATIONS.md#scenario-dual-venue-market-data-degradation)
- [`docs/runbook_data_incident.md`](runbook_data_incident.md)

---

### Feature Store Lag Alert

**Alert Definition**: `tradepulse_feature_store_sync_delay_seconds` p95 > 8 minutes for 3 windows

**SLA Impact**: Consumes Feature Store Synchronisation SLA error budget

**Immediate Response (< 15 minutes)**:
1. Acknowledge the alert in PagerDuty
2. Inspect the orchestrator job queue length via `tradepulse-cli feature-store status`
3. Check the latest Spark/Flake logs stored in `observability/logs/feature-store/`

**Diagnostics (15-30 minutes)**:
- Validate upstream ingestion backlog
- Inspect schema evolution events for conflicting migrations
- Confirm there is sufficient executor capacity in the compute pool

**Mitigation Steps**:
1. Scale the transformation workers with `tradepulse-cli feature-store scale --replicas +3`
2. Re-run the stuck batch `tradepulse-cli feature-store replay --batch <id>`
3. Pause low-priority backfills until lag recovers

**Communication**:
- Post status in `#data-ops` and inform affected strategy owners

**Resolution**:
- P95 delay < 4 minutes for 3 consecutive windows
- Incident ticket updated with root cause and preventive action

**Related Documents**:
- [`docs/OPERATIONS.md`](OPERATIONS.md#scenario-dual-venue-market-data-degradation)
- [`docs/operational_handbook.md`](operational_handbook.md)

---

### Reconciliation Drift Alert

**Alert Definition**: `tradepulse_position_drift_ratio` exceeds 0.8% for 2 consecutive windows

**SLA Impact**: Consumes Portfolio Reconciliation SLA error budget

**Immediate Response (< 10 minutes)**:
1. Acknowledge the alert and page the duty risk officer
2. Pull the latest reconciliation diff:

   ```bash
   tradepulse-cli reconciliation diff --window 5m --output /tmp/recon.json
   jq '.summary' /tmp/recon.json
   ```

3. Verify order state with `tradepulse-cli orders list --since 10m --status open`

**Diagnostics (10-20 minutes)**:
- Check for stale fills in broker API logs
- Ensure settlement jobs completed (`tradepulse-cli settlements status`)
- Confirm corporate action feeds did not adjust quantities unexpectedly

**Mitigation Steps**:
1. Initiate manual position sync following `docs/runbook_live_trading.md`
2. If broker missing fills, contact broker NOC and freeze strategy fan-out to 25%
3. Adjust hedge orders to neutralise delta while reconciliation completes

**Communication**:
- Update `#risk-ops` every 15 minutes
- Notify executive bridge if drift > 1.5% for 15 minutes

**Resolution**:
- Drift < 0.3% for 30 minutes and reconciliation diff clean
- Post-mortem entry created in `reports/live/<date>/postmortem.md`

**Related Documents**:
- [`docs/OPERATIONS.md`](OPERATIONS.md#scenario-cross-exchange-failover-rehearsal)
- [`docs/runbook_live_trading.md`](runbook_live_trading.md)

---

### Backtest Failures Alert

**Alert Definition**: At least one strategy backtest ended with an error in the last 30 minutes

**SLA Impact**: Low - Research operations

**Immediate Response (< 30 minutes)**:
1. **Check** failed backtest details:
   ```bash
   tradepulse-cli backtest list --status error --since 30m
   ```
2. **Review** error messages and stack traces

**Diagnostics**:
- Validate input data quality
- Check strategy configuration
- Review resource constraints
- Inspect dependency versions

**Mitigation Steps**:
1. **If data issue**: Fix data quality and re-run
2. **If config issue**: Correct configuration
3. **If resource issue**: Increase allocation or optimize
4. **If code bug**: File bug report and notify developer

**Communication**:
- Post to `#research` with details
- No escalation unless blocking critical work

**Resolution**:
- Verify successful backtest re-run
- Update documentation if configuration issue

---

### Optimization Slow Alert

**Alert Definition**: Average optimization duration exceeded two minutes

**SLA Impact**: Low - Research efficiency

**Immediate Response (< 1 hour)**:
1. **Monitor** trend over time
2. **Check** if new strategy added
3. **Review** optimization parameters

**Diagnostics**:
- Check computational complexity of objective function
- Review parameter space size
- Validate optimization algorithm settings
- Check resource availability

**Mitigation Steps**:
1. **Reduce** parameter search space
2. **Increase** worker resources
3. **Optimize** objective function implementation
4. **Consider** parallel optimization

**Communication**:
- Post to `#research` if sustained issue
- No immediate escalation

**Resolution**:
- Verify optimization times return to baseline
- Update optimization settings if needed

---

### Critical Incident Open Alert

**Alert Definition**: `TradePulseCriticalIncidentOpen` fires when `tradepulse_incidents_open{severity="critical"}` is non-zero, indicating at least one unresolved Sev1 incident.

**SLA Impact**: Blocks API, data, and lifecycle SLAs until the incident is resolved.

**Immediate Response (Immediate)**:
1. **Acknowledge** the incident page in PagerDuty and assume Incident Commander role.
2. **Open** the incident bridge (`#inc-critical-<timestamp>`) and invite on-call SRE, service owner, and communications lead.
3. **Review** the Production Operations Dashboard panels: `System Health Status`, `Open Incidents by Severity`, and `Incident Response Durations`.
4. **Pull** the latest incident list:
   ```bash
   tradepulse-cli incidents list --severity critical --status open --since 1h
   ```

**Diagnostics (0-10 minutes)**:
- Confirm incident scope and affected services in [`docs/incident_coordination_procedures.md`](incident_coordination_procedures.md).
- Verify mitigation owners and current tasks in the incident timeline.
- Check for correlated alerts (order latency, ingestion failures) to identify cascading impact.
- Validate that lifecycle checkpoints are not blocked in the dashboard.

**Mitigation Steps**:
1. **Assign** technical lead and communications lead per coordination procedures.
2. **Execute** the appropriate playbook (e.g. [`docs/runbook_live_trading.md`](runbook_live_trading.md) for trading outages).
3. **If multiple incidents**: triage by customer impact and delegate to additional commanders as required.
4. **Ensure** all mitigation actions are recorded in the incident timeline.

**Communication**:
- **Internal**: Post updates every 15 minutes in the incident channel, including mitigation status and next review time.
- **External**: Update status page when customer-facing impact is confirmed.
- **Escalation**: Notify VP Engineering if the incident persists beyond 30 minutes or if customer funds are at risk.

**Resolution**:
- Confirm `tradepulse_incidents_open{severity="critical"}` returns to zero.
- Capture post-incident actions and transition to postmortem workflow.
- Update lifecycle checkpoint `production-restoration` to `passed` in [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md).

**Related Documents**:
- [`docs/incident_coordination_procedures.md`](incident_coordination_procedures.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)
- [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md)

---

### Incident Acknowledgement SLA Alert

**Alert Definition**: `TradePulseIncidentAckSLA` triggers when the median acknowledgement time exceeds 5 minutes (`tradepulse_incident_ack_latency_seconds`).

**SLA Impact**: Consumes incident response error budget and risks breaching regulatory response targets.

**Immediate Response (< 10 minutes)**:
1. **Acknowledge** alert and verify incident queue ownership.
2. **Inspect** the Production Operations Dashboard `Incident Response Durations` panel for p50/p90 trends.
3. **Ensure** the on-call engineer is reachable; escalate if acknowledgement remains pending.
4. **Audit** recent pages:
   ```bash
   tradepulse-cli incidents audit --window 15m --fields severity,ack_time,responder
   ```

**Diagnostics (10-20 minutes)**:
- Determine if paging integration (PagerDuty, Slack) is degraded.
- Review on-call rota for gaps or outdated escalation paths.
- Check for alert storms causing responder overload.
- Validate that incident severity mappings are correct (no false criticals).

**Mitigation Steps**:
1. **Trigger** backup on-call rotation if primary responder is unavailable.
2. **Throttle** noisy alerts by applying maintenance windows or disabling non-actionable alerts.
3. **Escalate** to platform lead to redistribute incidents if workload exceeds capacity.
4. **Update** routing rules to ensure redundant notification channels are active.

**Communication**:
- Notify `#platform-ops` on acknowledgement delays and mitigation status.
- Provide ETA for restoration of paging health.
- Escalate to Duty Manager if SLA breach lasts beyond 30 minutes.

**Resolution**:
- Restore median acknowledgement below 5 minutes for at least 30 minutes.
- Validate alert by firing synthetic page to confirm end-to-end delivery.
- Document paging gap in incident review backlog.

**Related Documents**:
- [`docs/incident_coordination_procedures.md`](incident_coordination_procedures.md)
- [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)

---

### Lifecycle Checkpoint Blocked Alert

**Alert Definition**: `TradePulseLifecycleCheckpointBlocked` fires when `tradepulse_lifecycle_checkpoint_status{status="blocked"}` equals 1 for any checkpoint.

**SLA Impact**: Prevents lifecycle progression (startup, settlement, maintenance) and risks operational gaps.

**Immediate Response (< 5 minutes)**:
1. **Review** the `Lifecycle Checkpoint Status` table on the Production Operations Dashboard to identify the blocked checkpoint.
2. **Reference** [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md) for the blocked checkpoint procedure.
3. **Notify** the owning team in `#platform-ops` and assign an owner to clear the block.

**Diagnostics (5-15 minutes)**:
- Confirm prerequisite tasks (e.g. backups, compliance sign-off) are complete.
- Validate automation logs for failures or approvals waiting in workflow systems.
- Check runbook execution history for partial failures related to the checkpoint.
- Review change calendar for conflicting maintenance events.

**Mitigation Steps**:
1. **Execute** the corrective runbook for the checkpoint (e.g. [`docs/runbook_release_validation.md`](runbook_release_validation.md) for release gating).
2. **Re-run** failed automation tasks after addressing root cause.
3. **Request** manual approval if automation cannot recover within SLA.
4. **Document** temporary workarounds and ensure revalidation post-resolution.

**Communication**:
- Provide checkpoint status updates every 15 minutes until cleared.
- Escalate to platform lead if block persists beyond planned window.
- Notify dependent teams (trading, data) when checkpoint transitions resume.

**Resolution**:
- Confirm checkpoint status transitions to `passed` and automation completes successfully.
- Update lifecycle dashboard annotation with remediation summary.
- Capture preventive actions in lifecycle operations backlog.

**Related Documents**:
- [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md)
- [`docs/OPERATIONAL_ARTIFACTS_INDEX.md`](OPERATIONAL_ARTIFACTS_INDEX.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)

---

### Runbook Execution Failures Alert

**Alert Definition**: `TradePulseRunbookFailures` fires when `increase(tradepulse_runbook_executions_total{outcome="failed"}[15m]) > 0`.

**SLA Impact**: Signals degraded automation, risking delayed recovery or lifecycle tasks.

**Immediate Response (< 15 minutes)**:
1. **Inspect** the `Runbook Execution Outcomes` panel for failing runbooks and outcomes.
2. **Retrieve** detailed execution logs:
   ```bash
   tradepulse-cli runbooks history --runbook <name> --since 30m
   ```
3. **Contact** the runbook owner (see [`docs/OPERATIONAL_ARTIFACTS_INDEX.md`](OPERATIONAL_ARTIFACTS_INDEX.md) for ownership).

**Diagnostics (15-30 minutes)**:
- Determine if failures correlate with incident timelines.
- Check infrastructure dependencies (Kubernetes jobs, serverless functions).
- Validate credential access for automation accounts.
- Review recent code changes to runbook scripts.

**Mitigation Steps**:
1. **Execute** manual fallback procedure if automation cannot succeed.
2. **Patch** runbook configuration or revert recent changes causing failures.
3. **Create** hotfix branch for automation if code defect identified.
4. **Schedule** follow-up test run after fixes deployed.

**Communication**:
- Update `#platform-ops` with failing runbook, owner, and workaround plan.
- Escalate to platform lead if failure blocks critical lifecycle checkpoint.
- Notify incident commander if failure is tied to active incident mitigation.

**Resolution**:
- Confirm successful rerun of affected runbooks and corresponding metrics drop to zero failures.
- Document remediation steps and preventive fixes in automation backlog.
- Add regression tests or monitors for runbook reliability if absent.

**Related Documents**:
- [`docs/runbook_live_trading.md`](runbook_live_trading.md)
- [`docs/OPERATIONAL_ARTIFACTS_INDEX.md`](OPERATIONAL_ARTIFACTS_INDEX.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)

---

### Critical Incident Open Alert

**Alert Definition**: `TradePulseCriticalIncidentOpen` fires when `tradepulse_incidents_open{severity="critical"}` is non-zero, indicating at least one unresolved Sev1 incident.

**SLA Impact**: Blocks API, data, and lifecycle SLAs until the incident is resolved.

**Immediate Response (Immediate)**:
1. **Acknowledge** the incident page in PagerDuty and assume Incident Commander role.
2. **Open** the incident bridge (`#inc-critical-<timestamp>`) and invite on-call SRE, service owner, and communications lead.
3. **Review** the Production Operations Dashboard panels: `System Health Status`, `Open Incidents by Severity`, and `Incident Response Durations`.
4. **Pull** the latest incident list:
   ```bash
   tradepulse-cli incidents list --severity critical --status open --since 1h
   ```

**Diagnostics (0-10 minutes)**:
- Confirm incident scope and affected services in [`docs/incident_coordination_procedures.md`](incident_coordination_procedures.md).
- Verify mitigation owners and current tasks in the incident timeline.
- Check for correlated alerts (order latency, ingestion failures) to identify cascading impact.
- Validate that lifecycle checkpoints are not blocked in the dashboard.

**Mitigation Steps**:
1. **Assign** technical lead and communications lead per coordination procedures.
2. **Execute** the appropriate playbook (e.g. [`docs/runbook_live_trading.md`](runbook_live_trading.md) for trading outages).
3. **If multiple incidents**: triage by customer impact and delegate to additional commanders as required.
4. **Ensure** all mitigation actions are recorded in the incident timeline.

**Communication**:
- **Internal**: Post updates every 15 minutes in the incident channel, including mitigation status and next review time.
- **External**: Update status page when customer-facing impact is confirmed.
- **Escalation**: Notify VP Engineering if the incident persists beyond 30 minutes or if customer funds are at risk.

**Resolution**:
- Confirm `tradepulse_incidents_open{severity="critical"}` returns to zero.
- Capture post-incident actions and transition to postmortem workflow.
- Update lifecycle checkpoint `production-restoration` to `passed` in [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md).

**Related Documents**:
- [`docs/incident_coordination_procedures.md`](incident_coordination_procedures.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)
- [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md)

---

### Incident Acknowledgement SLA Alert

**Alert Definition**: `TradePulseIncidentAckSLA` triggers when the median acknowledgement time exceeds 5 minutes (`tradepulse_incident_ack_latency_seconds`).

**SLA Impact**: Consumes incident response error budget and risks breaching regulatory response targets.

**Immediate Response (< 10 minutes)**:
1. **Acknowledge** alert and verify incident queue ownership.
2. **Inspect** the Production Operations Dashboard `Incident Response Durations` panel for p50/p90 trends.
3. **Ensure** the on-call engineer is reachable; escalate if acknowledgement remains pending.
4. **Audit** recent pages:
   ```bash
   tradepulse-cli incidents audit --window 15m --fields severity,ack_time,responder
   ```

**Diagnostics (10-20 minutes)**:
- Determine if paging integration (PagerDuty, Slack) is degraded.
- Review on-call rota for gaps or outdated escalation paths.
- Check for alert storms causing responder overload.
- Validate that incident severity mappings are correct (no false criticals).

**Mitigation Steps**:
1. **Trigger** backup on-call rotation if primary responder is unavailable.
2. **Throttle** noisy alerts by applying maintenance windows or disabling non-actionable alerts.
3. **Escalate** to platform lead to redistribute incidents if workload exceeds capacity.
4. **Update** routing rules to ensure redundant notification channels are active.

**Communication**:
- Notify `#platform-ops` on acknowledgement delays and mitigation status.
- Provide ETA for restoration of paging health.
- Escalate to Duty Manager if SLA breach lasts beyond 30 minutes.

**Resolution**:
- Restore median acknowledgement below 5 minutes for at least 30 minutes.
- Validate alert by firing synthetic page to confirm end-to-end delivery.
- Document paging gap in incident review backlog.

**Related Documents**:
- [`docs/incident_coordination_procedures.md`](incident_coordination_procedures.md)
- [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)

---

### Lifecycle Checkpoint Blocked Alert

**Alert Definition**: `TradePulseLifecycleCheckpointBlocked` fires when `tradepulse_lifecycle_checkpoint_status{status="blocked"}` equals 1 for any checkpoint.

**SLA Impact**: Prevents lifecycle progression (startup, settlement, maintenance) and risks operational gaps.

**Immediate Response (< 5 minutes)**:
1. **Review** the `Lifecycle Checkpoint Status` table on the Production Operations Dashboard to identify the blocked checkpoint.
2. **Reference** [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md) for the blocked checkpoint procedure.
3. **Notify** the owning team in `#platform-ops` and assign an owner to clear the block.

**Diagnostics (5-15 minutes)**:
- Confirm prerequisite tasks (e.g. backups, compliance sign-off) are complete.
- Validate automation logs for failures or approvals waiting in workflow systems.
- Check runbook execution history for partial failures related to the checkpoint.
- Review change calendar for conflicting maintenance events.

**Mitigation Steps**:
1. **Execute** the corrective runbook for the checkpoint (e.g. [`docs/runbook_release_validation.md`](runbook_release_validation.md) for release gating).
2. **Re-run** failed automation tasks after addressing root cause.
3. **Request** manual approval if automation cannot recover within SLA.
4. **Document** temporary workarounds and ensure revalidation post-resolution.

**Communication**:
- Provide checkpoint status updates every 15 minutes until cleared.
- Escalate to platform lead if block persists beyond planned window.
- Notify dependent teams (trading, data) when checkpoint transitions resume.

**Resolution**:
- Confirm checkpoint status transitions to `passed` and automation completes successfully.
- Update lifecycle dashboard annotation with remediation summary.
- Capture preventive actions in lifecycle operations backlog.

**Related Documents**:
- [`docs/system_lifecycle_operations.md`](system_lifecycle_operations.md)
- [`docs/OPERATIONAL_ARTIFACTS_INDEX.md`](OPERATIONAL_ARTIFACTS_INDEX.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)

---

### Runbook Execution Failures Alert

**Alert Definition**: `TradePulseRunbookFailures` fires when `increase(tradepulse_runbook_executions_total{outcome="failed"}[15m]) > 0`.

**SLA Impact**: Signals degraded automation, risking delayed recovery or lifecycle tasks.

**Immediate Response (< 15 minutes)**:
1. **Inspect** the `Runbook Execution Outcomes` panel for failing runbooks and outcomes.
2. **Retrieve** detailed execution logs:
   ```bash
   tradepulse-cli runbooks history --runbook <name> --since 30m
   ```
3. **Contact** the runbook owner (see [`docs/OPERATIONAL_ARTIFACTS_INDEX.md`](OPERATIONAL_ARTIFACTS_INDEX.md) for ownership).

**Diagnostics (15-30 minutes)**:
- Determine if failures correlate with incident timelines.
- Check infrastructure dependencies (Kubernetes jobs, serverless functions).
- Validate credential access for automation accounts.
- Review recent code changes to runbook scripts.

**Mitigation Steps**:
1. **Execute** manual fallback procedure if automation cannot succeed.
2. **Patch** runbook configuration or revert recent changes causing failures.
3. **Create** hotfix branch for automation if code defect identified.
4. **Schedule** follow-up test run after fixes deployed.

**Communication**:
- Update `#platform-ops` with failing runbook, owner, and workaround plan.
- Escalate to platform lead if failure blocks critical lifecycle checkpoint.
- Notify incident commander if failure is tied to active incident mitigation.

**Resolution**:
- Confirm successful rerun of affected runbooks and corresponding metrics drop to zero failures.
- Document remediation steps and preventive fixes in automation backlog.
- Add regression tests or monitors for runbook reliability if absent.

**Related Documents**:
- [`docs/runbook_live_trading.md`](runbook_live_trading.md)
- [`docs/OPERATIONAL_ARTIFACTS_INDEX.md`](OPERATIONAL_ARTIFACTS_INDEX.md)
- [`observability/dashboards/tradepulse-production-operations.json`](../observability/dashboards/tradepulse-production-operations.json)

---

## Escalation Matrix


### Severity: Critical
- **Response Time**: < 5 minutes
- **Primary**: On-call SRE
- **Secondary**: Platform Lead (if no resolution in 15 min)
- **Executive**: VP Engineering (if no resolution in 30 min or customer impact)

### Severity: Warning
- **Response Time**: < 15 minutes
- **Primary**: On-call SRE
- **Secondary**: Service owner (if no resolution in 30 min)
- **Executive**: No automatic escalation

### Severity: Info
- **Response Time**: < 1 hour
- **Primary**: Service owner
- **Secondary**: None
- **Executive**: None

## SLA Breach Procedures

### When Error Budget is Exhausted
1. **Declare** error budget exhaustion incident
2. **Freeze** non-critical deployments
3. **Convene** reliability review meeting within 24 hours
4. **Prioritize** stability work over new features
5. **Report** to executive team with recovery plan

### When Approaching Error Budget Depletion (>75%)
1. **Alert** engineering leadership
2. **Review** recent incidents for patterns
3. **Accelerate** reliability improvements
4. **Increase** monitoring and alerting coverage
5. **Consider** deployment freeze if >90%

## Communication Templates

### Initial Incident Notification
```
🚨 INCIDENT: [Alert Name]
Severity: [Critical/Warning/Info]
Started: [Timestamp UTC]
Impact: [Description of user/system impact]
Status: Investigating
Updates: Every [5/15/30] minutes in #inc-[channel]
Incident Commander: @[name]
```

### Status Update Template
```
📊 UPDATE: [Alert Name] - [HH:MM UTC]
Current Status: [Investigating/Mitigating/Resolved]
Actions Taken:
- [Action 1]
- [Action 2]
Impact: [Current impact level]
Next Update: [Timestamp]
```

### Resolution Notification
```
✅ RESOLVED: [Alert Name]
Duration: [Duration]
Root Cause: [Brief description]
Resolution: [What fixed it]
Follow-up: Postmortem in [reports/incidents/YYYY/incident-XXX/]
```

## Postmortem Requirements

### When Required
- Any critical alert lasting > 15 minutes
- Any SLA breach
- Any alert requiring executive escalation
- Any incident with customer impact

### Timeline
- **Draft**: Within 24 hours
- **Review**: Within 48 hours
- **Finalized**: Within 72 hours

### Contents
- Timeline of events
- Root cause analysis (5 whys)
- Action items with owners and due dates
- Preventive measures
- SLA impact calculation

### Storage
- File in `reports/incidents/YYYY/incident-XXX/`
- Use template from [`reports/incidents/postmortem_template.md`](../reports/incidents/postmortem_template.md)
- Link to relevant alert definitions and playbooks

---

## Maintenance and Updates

This playbook should be reviewed and updated:
- After every major incident
- Quarterly during reliability reviews
- When new alerts are added
- When SLAs are modified

Last Updated: 2025-11-11
Version: 1.1
Owner: SRE Team
