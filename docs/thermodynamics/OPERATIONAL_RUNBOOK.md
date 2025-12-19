# TACL Operational Runbook

## Overview

This runbook provides operational procedures for managing the Thermodynamic Autonomic Control Layer (TACL) in production environments.

## Table of Contents

1. [System Overview](#system-overview)
2. [Monitoring and Alerts](#monitoring-and-alerts)
3. [Normal Operations](#normal-operations)
4. [Crisis Response](#crisis-response)
5. [Manual Overrides](#manual-overrides)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance Procedures](#maintenance-procedures)
8. [Compliance and Audit](#compliance-and-audit)

## System Overview

### Architecture Components

- **ThermoController**: Main control loop managing free energy
- **Energy Validator**: Validates metrics against energy thresholds
- **Link Activator**: Hot-swaps protocols between services
- **Recovery Agent**: Q-learning based adaptive recovery
- **Crisis GA**: Genetic algorithm for topology evolution
- **CNS Stabilizer**: Signal processing and homeostasis
- **Audit Logger**: Immutable decision trail

### Key Metrics

- **Free Energy (F)**: Target ≤ 1.35
- **Energy Derivative (dF/dt)**: Target < 0 (descent)
- **Circuit Breaker**: Should be inactive
- **Monotonic Violations**: Should be minimal

## Monitoring and Alerts

### Primary Endpoints

```bash
# System status
curl http://localhost:8080/thermo/status

# Historical data
curl http://localhost:8080/thermo/history?limit=100

# Crisis statistics
curl http://localhost:8080/thermo/crisis

# Protocol activations
curl http://localhost:8080/thermo/activations
```

### Alert Thresholds

| Alert Level | Condition | Action |
|-------------|-----------|--------|
| **INFO** | F > 1.20 | Monitor closely |
| **WARNING** | F > 1.30 | Investigate immediately |
| **CRITICAL** | F > 1.35 | Rollback required |
| **EMERGENCY** | Circuit breaker active | Manual intervention |

### Prometheus Queries

```promql
# Current free energy
system_free_energy

# Energy rate of change
system_dFdt

# Monotonic violations (should be rare)
rate(monotonic_violations_total[5m])

# Circuit breaker state (should be 0)
circuit_breaker_active

# CNS stabilizer health
homeostasis_integrity_ratio
```

## Normal Operations

### Daily Checks

```bash
# 1. Verify free energy is within bounds
curl -s http://localhost:8080/thermo/status | jq '.current_F'

# 2. Check for sustained energy rise
curl -s http://localhost:8080/thermo/history?limit=10 | jq '.records[].F'

# 3. Verify circuit breaker is inactive
curl -s http://localhost:8080/thermo/status | jq '.crisis_mode'

# 4. Review recent topology changes
curl -s http://localhost:8080/thermo/history?limit=5 | jq '.records[].topology_changes'

# 5. Check protocol activation success rate
curl -s http://localhost:8080/thermo/activations | jq '.activations[-10:]'
```

### Weekly Reviews

1. Export audit logs for compliance:
   ```bash
   cat /var/log/tradepulse/thermo_audit.jsonl | tail -10080 > weekly_audit.jsonl
   ```

2. Analyze energy trends:
   ```bash
   python scripts/analyze_thermo_trends.py --period 7d
   ```

3. Review monotonic violations:
   ```bash
   grep "monotonic_violation" /var/log/tradepulse/thermo_audit.jsonl | wc -l
   ```

## Crisis Response

### Crisis Levels

#### ELEVATED Crisis (F deviation 10-25%)

**Symptoms:**
- Free energy elevated but below critical
- Latency spike < 2.0x baseline
- System still responsive

**Response:**
1. Monitor closely, system will self-recover
2. Verify recovery agent is active
3. Check for external load spikes
4. Review recent deployments

**Commands:**
```bash
# Check crisis mode
curl http://localhost:8080/thermo/crisis | jq '.current_mode'

# Monitor recovery progress
watch -n 1 'curl -s http://localhost:8080/thermo/status | jq ".current_F, .dF_dt"'
```

#### CRITICAL Crisis (F deviation > 25%)

**Symptoms:**
- Free energy in critical zone
- Significant latency degradation
- Possible circuit breaker activation

**Response:**
1. Page on-call engineer immediately
2. Prepare for potential rollback
3. Gather diagnostic data
4. Consider manual override if system cannot recover

**Commands:**
```bash
# Capture current state
curl http://localhost:8080/thermo/status > crisis_state_$(date +%s).json

# Export telemetry
curl http://localhost:8080/thermo/history?limit=1000 > crisis_history_$(date +%s).json

# Check GA evolution progress
curl http://localhost:8080/thermo/crisis | jq '.evolution_attempts'
```

### Circuit Breaker Active

**Symptoms:**
- Circuit breaker flag is true
- Topology mutations blocked
- Free energy not improving

**Response:**

1. **Do NOT override immediately** - Circuit breaker prevents unsafe changes
2. Investigate root cause
3. Verify metrics are accurate
4. If false positive confirmed, prepare manual override

## Manual Overrides

### When to Override

Manual override is appropriate when:
- Circuit breaker is false positive (metrics error)
- External intervention has resolved root cause
- Dual approval from Duty Officer + Staff Engineer obtained

### Override Procedure

1. **Obtain Dual Approval:**
   ```bash
   # Thermodynamic Duty Officer must approve
   # Platform Staff Engineer must approve
   # Document in incident ticket
   ```

2. **Generate Override Token:**
   ```bash
   # Token should be generated by security team
   export THERMO_OVERRIDE_TOKEN="<secure-token>"
   ```

3. **Execute Override:**
   ```bash
   curl -X POST http://localhost:8080/thermo/override \
     -H "Content-Type: application/json" \
     -d '{
       "token": "'"$THERMO_OVERRIDE_TOKEN"'",
       "reason": "False positive after load balancer fix - Ticket #12345"
     }'
   ```

4. **Verify System Recovery:**
   ```bash
   # Monitor for 5 minutes
   watch -n 5 'curl -s http://localhost:8080/thermo/status | jq ".current_F, .circuit_breaker_active"'
   ```

5. **Document in Audit Log:**
   - Reason for override
   - Approving engineers
   - Ticket reference
   - Post-override metrics

### Override Token Management

```bash
# Generate new token (security team only)
python scripts/generate_thermo_token.py --duration 1h > token.txt

# Rotate token after use
unset THERMO_OVERRIDE_TOKEN
```

## Troubleshooting

### High Free Energy (F > 1.30)

**Check:**
1. Recent deployments or configuration changes
2. Latency metrics accuracy
3. Resource utilization (CPU, memory)
4. External dependencies health

**Commands:**
```bash
# Detailed metrics breakdown
curl http://localhost:8080/thermo/status | jq '.metrics'

# Recent topology changes
curl http://localhost:8080/thermo/history?limit=20 | \
  jq '.records[] | select(.topology_changes | length > 0)'

# Bottleneck identification
curl http://localhost:8080/thermo/status | jq '.bottleneck_edge, .max_edge_cost'
```

### Sustained Energy Rise

**Check:**
1. Is dF/dt consistently positive?
2. Are topology changes being rejected?
3. Is recovery agent converging?

**Commands:**
```bash
# Energy derivative trend
curl http://localhost:8080/thermo/history?limit=50 | jq '.records[].dF_dt'

# Rejection reasons
grep "rejected" /var/log/tradepulse/thermo_audit.jsonl | tail -20
```

### Protocol Activation Failures

**Check:**
1. Network connectivity between services
2. RDMA/CRDT/gRPC health
3. Fallback chain execution

**Commands:**
```bash
# Recent activation failures
curl http://localhost:8080/thermo/activations | \
  jq '.activations[] | select(.success == false)'

# Protocol availability
systemctl status tradepulse-protocols
```

## Maintenance Procedures

### Planned Maintenance

1. **Before Maintenance:**
   ```bash
   # Capture baseline
   curl http://localhost:8080/thermo/status > pre_maintenance_baseline.json
   
   # Increase monitoring
   # Set alert suppression window
   ```

2. **During Maintenance:**
   ```bash
   # Monitor free energy continuously
   watch -n 2 'curl -s http://localhost:8080/thermo/status | jq ".current_F"'
   ```

3. **After Maintenance:**
   Use the canonical comparator script at [`scripts/compare_states.py`](../../scripts/compare_states.py) (repository root) to diff pre/post states.
   ```bash
   # Verify energy returned to baseline
   curl http://localhost:8080/thermo/status > post_maintenance_state.json
   
   # Compare with baseline (canonical comparator; replaces compare_thermo_states.py)
   python scripts/compare_states.py \
     pre_maintenance_baseline.json \
     post_maintenance_state.json
   ```

### Controller Restart

```bash
# Graceful shutdown
systemctl stop tradepulse-thermo-controller

# Verify audit logs are flushed
sync

# Restart
systemctl start tradepulse-thermo-controller

# Verify initialization
journalctl -u tradepulse-thermo-controller -f | grep "initialized"

# Check initial free energy
sleep 5
curl http://localhost:8080/thermo/status | jq '.current_F'
```

### Configuration Updates

```bash
# Backup current config
cp /etc/tradepulse/thermo_config.yaml /etc/tradepulse/thermo_config.yaml.backup

# Update configuration
vim /etc/tradepulse/thermo_config.yaml

# Validate configuration
python -c "from runtime.thermo_config import ThermoConfig; ThermoConfig.from_yaml('/etc/tradepulse/thermo_config.yaml'); print('Valid')"

# Apply (requires restart)
systemctl restart tradepulse-thermo-controller
```

## Compliance and Audit

### Audit Log Retention

Audit logs must be retained for **7 years** for regulatory compliance.

```bash
# Verify audit log location
ls -lh /var/log/tradepulse/thermo_audit.jsonl

# Rotate logs monthly
logrotate -f /etc/logrotate.d/tradepulse-thermo

# Archive to long-term storage
aws s3 cp /var/log/tradepulse/thermo_audit.jsonl.$(date +%Y%m).gz \
  s3://tradepulse-compliance/thermo-audit/
```

### Compliance Reporting

```bash
# Generate monthly compliance report
python scripts/generate_thermo_compliance_report.py \
  --start $(date -d "1 month ago" +%Y-%m-01) \
  --end $(date +%Y-%m-%d) \
  --output compliance_report_$(date +%Y%m).pdf
```

### Dual Approval Audit

```bash
# Review all manual overrides
grep "manual_override" /var/log/tradepulse/thermo_audit.jsonl | \
  jq -r '[.ts, .override_reason] | @tsv'

# Verify dual approval documentation
# Check incident tickets for approval records
```

## Emergency Contacts

| Role | Responsibility | Contact |
|------|----------------|---------|
| Thermodynamic Duty Officer | Approve overrides | Rotating weekly |
| Platform Staff Engineer | System expertise | On-call rotation |
| SRE Team Lead | Escalation point | 24/7 pager |
| Security Team | Token management | security@tradepulse.io |

## References

- [TACL Architecture](./TACL.md)
- [Metrics Formalization](./METRICS_FORMALIZATION.md)
- [Energy Validator API](../../runtime/energy_validator.py)
- [Configuration Guide](../../runtime/thermo_config.py)

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-16 | 1.0 | Initial runbook |
