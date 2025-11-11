# SLA and Alert Response Playbooks

This document provides comprehensive response procedures for every alert defined
in TradePulse, mapping alerts to SLAs, escalation paths, and resolution
playbooks. Use this as the primary reference when alerts fire in production.
It also links each production alert to the telemetry surfaced by the
`/api/v1/dashboard/production` endpoint so responders can pivot directly from
monitoring signals to the correct operational runbooks.

## Quick Reference Matrix

| Alert Name | Severity | SLA Impact | Response Time | Playbook Section |
|------------|----------|------------|---------------|------------------|
| TradePulseOrderErrorRate | Critical | High | < 5 min | [Order Error Rate](#order-error-rate-alert) |
| TradePulseOrderLatency | Warning | Medium | < 15 min | [Order Latency](#order-latency-alert) |
| TradePulseOrderAckLatency | Warning | Medium | < 15 min | [Order Acknowledgement Latency](#order-acknowledgement-latency-alert) |
| TradePulseSignalToFillLatency | Critical | High | < 5 min | [Signal to Fill Latency](#signal-to-fill-latency-alert) |
| TradePulseDataIngestionFailures | Critical | High | < 5 min | [Data Ingestion Failures](#data-ingestion-failures-alert) |
| TradePulseDataFreshness | Warning | Medium | < 15 min | [Data Freshness](#data-freshness-alert) |
| TradePulseBacktestFailures | Warning | Low | < 30 min | [Backtest Failures](#backtest-failures-alert) |
| TradePulseOptimizationSlow | Info | Low | < 1 hour | [Optimization Slow](#optimization-slow-alert) |

## Dashboard Linked Alert Catalogue

### Latency and Availability

| Alert ID | Trigger Source | SLA / Target | Response Owner | Playbook |
| --- | --- | --- | --- | --- |
| `cb-half-open`, `cb-open` | Prometheus alert `TradePulseSignalToFillLatency` and circuit breaker telemetry | p95 signal-to-fill latency ≤ 650 ms (`observability/slo_policies.json`) | Execution engineer (primary), SRE (secondary) | 1. Confirm circuit breaker reason via dashboard.<br>2. Run [`docs/incident_playbooks.md#execution-lag`](incident_playbooks.md#execution-lag).<br>3. Capture Grafana panel snapshots and attach to incident ticket. |
| `kill-switch-drill`, `kill-switch-engaged` | Kill switch events emitted by `execution.risk.RiskManager` | Platform availability ≥ 99.5% | Duty officer | 1. Verify whether the switch was part of a scheduled drill.<br>2. If unscheduled, escalate to production lead, freeze deployments, and follow [`docs/incident_response_lifecycle.md`](incident_response_lifecycle.md). |
| `api-latency-burn` | Prometheus burn-rate alert for `tradepulse-api-latency` | HTTP error budget (1.5% over 5m) | API on-call | 1. Page API on-call, inform communications channel `#status-tradepulse`.<br>2. Enable rate limiting overrides if required.<br>3. Reference mitigation steps in [`docs/incident_playbooks.md#execution-lag`](incident_playbooks.md#execution-lag). |

### Data Quality and Ingestion

| Alert ID | Trigger Source | SLA / Target | Response Owner | Playbook |
| --- | --- | --- | --- | --- |
| `ingestion-freshness` | `TradePulseDataFreshness` Prometheus alert | Ingestion lag < 5 minutes | Data engineering | 1. Inspect ingestion job logs (dashboard `orders.rejectionRate` often spikes during lag).<br>2. Launch [`docs/runbook_data_incident.md`](runbook_data_incident.md).<br>3. Communicate expected recovery time to quantitative leads. |
| `ingestion-failure` | `TradePulseDataIngestionFailures` Prometheus alert | Ingestion success rate ≥ 99% | Data engineering | 1. Use `tradepulse-cli ingest --output jsonl` to reproduce failure.<br>2. If multiple venues affected, fail over to redundant feed handlers.<br>3. File incident ticket referencing `reports/incidents/` templates. |

### Order Health

| Alert ID | Trigger Source | SLA / Target | Response Owner | Playbook |
| --- | --- | --- | --- | --- |
| `order-rejection-rate` | Derived from dashboard metric `orders.rejectionRate` > 0.5% | Rejection ratio ≤ 0.5% (5 minute window) | Execution operations | 1. Enable `strategy.reject_guard` using remote control API.<br>2. Audit rejection reasons (`tradepulse-cli exec --output jsonl`).<br>3. Follow mitigation checklist in [`docs/incident_playbooks.md#rejected-orders`](incident_playbooks.md#rejected-orders). |
| `circuit-trips` | Dashboard metric `orders.circuitTrips` > 0 in consecutive windows | Circuit trip frequency ≤ 2 per hour | SRE with compliance on standby | 1. Review circuit breaker timeline and cooldown on dashboard.<br>2. Validate guardrail configuration from `configs/risk.yaml`.<br>3. If trips persist, escalate using [`docs/incident_response_lifecycle.md`](incident_response_lifecycle.md). |

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

Last Updated: 2025-11-10
Version: 1.1
Owner: SRE Team
