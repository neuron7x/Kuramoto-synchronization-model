# Thermodynamics (TACL) Complete Index

## Quick Reference

| Resource | Type | Purpose |
|----------|------|---------|
| [TACL.md](../TACL.md) | Specification | Original TACL specification |
| [README.md](./README.md) | Documentation Hub | Central documentation index |
| [METRICS_FORMALIZATION.md](./METRICS_FORMALIZATION.md) | Formalization | Mathematical foundations |
| [OPERATIONAL_RUNBOOK.md](./OPERATIONAL_RUNBOOK.md) | Operations | Production procedures |

## Code Modules

### Core Runtime

| Module | Lines | Purpose |
|--------|-------|---------|
| `runtime/energy_validator.py` | 332 | Energy validation engine |
| `runtime/thermo_config.py` | 356 | Configuration management |
| `runtime/thermo_controller.py` | 1368 | Main control loop |
| `runtime/thermo_api.py` | 115 | FastAPI telemetry endpoints |
| `runtime/link_activator.py` | - | Protocol hot-swapping |
| `runtime/recovery_agent.py` | - | Q-learning adaptive recovery |
| `runtime/cns_stabilizer.py` | - | Signal processing |

### Supporting Modules

| Module | Purpose |
|--------|---------|
| `evolution/crisis_ga.py` | Crisis-aware genetic algorithm |
| `runtime/dual_approval.py` | Dual approval system |
| `runtime/kill_switch.py` | Emergency kill switch |
| `runtime/behavior_contract.py` | TACL safety gates |
| `runtime/filters/vlpo_core_filter.py` | Outlier filtering |

## Configuration

### Files

- **`config/thermo_config.yaml`**: Default configuration with all parameters
- **Environment Variables**:
  - `THERMO_CONTROL_TEMPERATURE`: Control temperature (default: 0.60)
  - `THERMO_MAX_ENERGY`: Max acceptable energy (default: 1.35)
  - `THERMO_AUDIT_LOG_PATH`: Audit log path
  - `THERMO_DUAL_TOKEN`: Dual approval token
  - `THERMO_OVERRIDE_TOKEN`: Manual override token

### Configuration Sections

1. **Crisis Thresholds**: Normal/Elevated/Critical detection
2. **Safety Constraints**: Monotonic descent, circuit breaker
3. **Genetic Algorithm**: Population sizes, mutation rates
4. **Recovery Agent**: Q-learning parameters
5. **Link Activator**: Protocol mappings and priorities
6. **Telemetry**: Audit logs, export settings
7. **CNS Stabilizer**: Kalman/PID parameters
8. **VLPO Filter**: Outlier rejection settings
9. **Dual Approval**: Token management

## Examples

### Code Examples

| File | Description |
|------|-------------|
| `examples/energy_validation_example.py` | Basic energy validation |
| `examples/thermo_hpc_ai_integration.py` | HPC-AI integration demo |
| `examples/ecs_regulator_demo.py` | ECS integration |

### Example Snippets

**Basic Validation:**
```python
from runtime.energy_validator import EnergyValidator

validator = EnergyValidator()
metrics = {"latency_p95": 75.0, "cpu_burn": 0.65, ...}
result = validator.compute_free_energy(metrics)
```

**Controller Usage:**
```python
from runtime.thermo_controller import ThermoController

controller = ThermoController(graph)
controller.control_step()
print(controller.get_current_F())
```

**CLI Validation:**
```bash
python scripts/validate_energy.py \
  --metric latency_p95=75.0 \
  --metric cpu_burn=0.65 \
  --output report.json
```

## Tests

### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_energy_validator.py` | 30+ | Energy validation |
| `tests/test_thermo_hpc_ai.py` | - | HPC-AI integration |
| `tests/test_thermo_fallback.py` | - | Fallback mechanisms |
| `tests/test_thermo_manual_override.py` | - | Manual overrides |
| `tests/test_thermo_violations.py` | - | Constraint violations |
| `tests/test_thermo_audit.py` | - | Audit trail |
| `tests/runtime/test_thermo_agent_bridge.py` | - | Agent integration |
| `tests/sandbox/test_thermo_prototype.py` | - | Prototype validation |

### Running Tests

```bash
# All thermodynamics tests
pytest tests/test_thermo*.py -v

# Energy validator tests
pytest tests/test_energy_validator.py -v

# With coverage
pytest tests/test_thermo*.py --cov=runtime --cov-report=html
```

## CLI Tools

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/validate_energy.py` | Energy validation CLI |
| `scripts/admission_check.py` | CI gate for monotonicity |

### Command Reference

**Validate metrics:**
```bash
python scripts/validate_energy.py metrics.json
```

**Inline validation:**
```bash
python scripts/validate_energy.py \
  --metric latency_p95=75.0 \
  --metric latency_p99=100.0 \
  --verbose
```

**Export report:**
```bash
python scripts/validate_energy.py metrics.json \
  --output .ci_artifacts/energy_validation.json
```

**Show config:**
```bash
python scripts/validate_energy.py --show-config
```

## API Endpoints

### FastAPI Routes

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/thermo/status` | GET | Current system state |
| `/thermo/history` | GET | Historical telemetry |
| `/thermo/crisis` | GET | Crisis statistics |
| `/thermo/activations` | GET | Protocol activation history |
| `/thermo/reset` | POST | Reset controller |
| `/thermo/override` | POST | Manual override |

### Usage

**Check status:**
```bash
curl http://localhost:8080/thermo/status | jq
```

**Get history:**
```bash
curl http://localhost:8080/thermo/history?limit=100 | jq
```

**Manual override:**
```bash
curl -X POST http://localhost:8080/thermo/override \
  -H "Content-Type: application/json" \
  -d '{"token": "...", "reason": "..."}'
```

## Prometheus Metrics

### Exported Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `system_free_energy` | Gauge | Current F value |
| `system_dFdt` | Gauge | Energy derivative |
| `monotonic_violations_total` | Counter | Constraint violations |
| `homeostasis_integrity_ratio` | Gauge | CNS stabilizer health |
| `stabilizer_phase_total` | Counter | Phase transitions |
| `stabilizer_veto_events_total` | Counter | Hard veto decisions |
| `tacl_delta_f` | Histogram | ΔF observations |

### Queries

**Current free energy:**
```promql
system_free_energy
```

**Violation rate:**
```promql
rate(monotonic_violations_total[5m])
```

**Energy trend:**
```promql
deriv(system_free_energy[5m])
```

## Documentation

### Main Documents

1. **[TACL.md](../TACL.md)** (Updated)
   - Original specification
   - Metrics and thresholds
   - Acceptable energy range
   - Programmatic implementation references

2. **[README.md](./README.md)** (New)
   - Documentation hub
   - Quick start guide
   - Usage examples
   - Troubleshooting

3. **[METRICS_FORMALIZATION.md](./METRICS_FORMALIZATION.md)** (New)
   - Mathematical formalization
   - Helmholtz free energy
   - Crisis detection algorithms
   - Recovery procedures
   - Bond evolution

4. **[OPERATIONAL_RUNBOOK.md](./OPERATIONAL_RUNBOOK.md)** (New)
   - Monitoring and alerts
   - Crisis response
   - Manual overrides
   - Troubleshooting
   - Maintenance procedures

### Related Documents

- **[PATENTS.md](../../PATENTS.md)**: Patent filing for TACL
- **[HPC_AI_FINAL_REPORT.md](../../HPC_AI_FINAL_REPORT.md)**: HPC-AI integration
- **[SYSTEM_OPTIMIZATION_SUMMARY.md](../../SYSTEM_OPTIMIZATION_SUMMARY.md)**: System optimizations

## Operational Procedures

### Daily Operations

1. **Morning Checklist**:
   - Check free energy: `curl localhost:8080/thermo/status`
   - Verify circuit breaker inactive
   - Review topology changes
   - Check violation count

2. **Monitoring**:
   - Alert on F > 1.20 (warning)
   - Alert on F > 1.30 (critical)
   - Page on F > 1.35 (emergency)
   - Monitor circuit breaker state

3. **Weekly Review**:
   - Export audit logs
   - Analyze energy trends
   - Review violation patterns
   - Check compliance

### Crisis Response

**ELEVATED (10-25% deviation):**
- Monitor closely
- System should self-recover
- Check for external load spikes

**CRITICAL (>25% deviation):**
- Page on-call immediately
- Prepare for rollback
- Gather diagnostics
- Consider manual override

**Circuit Breaker Active:**
- Do NOT override immediately
- Investigate root cause
- Verify metrics accuracy
- Obtain dual approval if needed

### Maintenance

**Before Maintenance:**
```bash
curl localhost:8080/thermo/status > baseline.json
```

**After Maintenance:**
```bash
curl localhost:8080/thermo/status > post_maintenance.json
python scripts/compare_states.py baseline.json post_maintenance.json
```

## Compliance

### Audit Requirements

- **Retention**: 7 years minimum
- **Format**: JSONL with full decision context
- **Location**: `/var/log/tradepulse/thermo_audit.jsonl`
- **Rotation**: Monthly with archival to S3

### Dual Approval

Required for:
- Manual overrides
- Topology mutations in CRITICAL mode
- Protocol activations with high cost
- Circuit breaker overrides

### Compliance Reporting

```bash
python scripts/generate_thermo_compliance_report.py \
  --start 2025-01-01 \
  --end 2025-01-31 \
  --output report.pdf
```

## Performance

### Benchmarks

| Operation | Latency | Throughput |
|-----------|---------|------------|
| Control step | <1ms | 1000 Hz |
| Energy computation | <100μs | 10,000 Hz |
| GA evolution | ~10ms | 100 Hz |
| Protocol activation | <5s | - |

### Scaling Limits

- **Nodes**: Tested up to 100
- **Edges**: Tested up to 500
- **History**: 10,000 records retained
- **Telemetry rate**: 1000 samples/sec

## Troubleshooting

### Common Issues

**High Free Energy:**
1. Check recent deployments
2. Verify metrics accuracy
3. Review bottleneck edge
4. Check resource utilization

**Protocol Activation Failures:**
1. Verify network connectivity
2. Check protocol health
3. Review fallback chain
4. Inspect link activator logs

**Circuit Breaker Won't Reset:**
1. Verify root cause resolved
2. Check sustained energy rise
3. Review violation history
4. Consider manual override with dual approval

## Contributing

### Adding New Metrics

1. Update `EnergyConfig` in `runtime/energy_validator.py`
2. Add threshold to `config/thermo_config.yaml`
3. Update `METRICS_FORMALIZATION.md`
4. Add tests in `tests/test_energy_validator.py`
5. Update documentation

### Modifying Algorithms

1. Maintain backward compatibility
2. Add comprehensive tests
3. Update formalization document
4. Benchmark performance impact
5. Update operational runbook

## References

### Academic Papers

- Friston, K. (2010). The free-energy principle: a unified brain theory?
- Helmholtz, H. (1882). Die Thermodynamik chemischer Vorgänge

### Implementation References

- **Energy Validator**: `runtime/energy_validator.py`
- **Configuration**: `runtime/thermo_config.py`
- **Controller**: `runtime/thermo_controller.py`
- **API**: `runtime/thermo_api.py`

### External Links

- [GitHub Repository](https://github.com/neuron7x/TradePulse)
- [CI/CD Pipeline](../.github/workflows/thermo-evolution.yml)
- [Prometheus Metrics](http://localhost:9090)
- [API Documentation](http://localhost:8080/docs)

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-16 | 1.0 | Initial comprehensive implementation |
| 2025-11-16 | 1.0 | Added documentation hub and formalization |
| 2025-11-16 | 1.0 | Created operational runbook |
| 2025-11-16 | 1.0 | Implemented energy validator module |
