---
owner: neuro@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Thermodynamics (TACL) Documentation

This directory contains comprehensive documentation for the **Thermodynamic Autonomic Control Layer (TACL)** in TradePulse.

## Overview

TACL is a self-regulating control system that manages the TradePulse distributed topology as a physical system. It applies thermodynamic principles (specifically the Free Energy Principle from neuroscience) to autonomous system optimization while maintaining formal safety guarantees.

## Key Concepts

### Free Energy Principle

TACL measures and minimizes the system's Helmholtz free energy:

```
F = U - T·S
```

Where:
- **F**: Free energy (system inefficiency, target: F ≤ 1.35)
- **U**: Internal energy (weighted penalties from metrics)
- **T**: Control temperature (0.60)
- **S**: Stability (available headroom)

### Monotonic Descent Constraint

The core safety guarantee: **F_new ≤ F_old + ε**

No topology change is permitted to increase free energy beyond the tolerance budget **ε**.

### Crisis-Aware Adaptation

System automatically detects three crisis modes:
- **NORMAL**: Baseline operation
- **ELEVATED**: 10-25% free energy deviation
- **CRITICAL**: >25% deviation

Genetic algorithm and recovery agent scale their aggressiveness based on crisis severity.

## Documentation Files

### [TACL.md](../TACL.md)
Original TACL specification defining:
- Metrics and thresholds
- Acceptable energy range (F ≤ 1.35)
- Dual approval requirements

### [METRICS_FORMALIZATION.md](./METRICS_FORMALIZATION.md)
Comprehensive mathematical formalization including:
- Helmholtz free energy computation
- Penalty and stability calculations
- Crisis detection algorithms
- Recovery agent Q-learning
- Bond evolution via genetic algorithm
- Protocol activation procedures
- Validation procedures

### [OPERATIONAL_RUNBOOK.md](./OPERATIONAL_RUNBOOK.md)
Operational procedures for production:
- Monitoring and alerts
- Normal operations checklist
- Crisis response procedures
- Manual override protocols
- Troubleshooting guides
- Maintenance procedures
- Compliance and audit

## Implementation

### Core Modules

| Module | Purpose |
|--------|---------|
| `runtime/thermo_controller.py` | Main control loop orchestrator |
| `runtime/energy_validator.py` | Energy computation and validation |
| `runtime/thermo_config.py` | Centralized configuration |
| `runtime/thermo_api.py` | FastAPI telemetry endpoints |
| `runtime/link_activator.py` | Protocol hot-swapping |
| `runtime/recovery_agent.py` | Q-learning adaptive recovery |
| `evolution/crisis_ga.py` | Crisis-aware genetic algorithm |
| `runtime/cns_stabilizer.py` | Signal processing and homeostasis |

### Configuration

Default configuration: `config/thermo_config.yaml`

Load configuration:
```python
from runtime.thermo_config import ThermoConfig

config = ThermoConfig.from_yaml("config/thermo_config.yaml")
# Or load from environment
config = ThermoConfig.from_env()
```

### Usage Examples

#### Energy Validation

```python
from runtime.energy_validator import EnergyValidator

validator = EnergyValidator()

metrics = {
    "latency_p95": 75.0,
    "latency_p99": 100.0,
    "coherency_drift": 0.05,
    "cpu_burn": 0.65,
    "mem_cost": 5.5,
    "queue_depth": 25.0,
    "packet_loss": 0.003,
}

result = validator.compute_free_energy(metrics)
print(f"Free Energy: {result.free_energy:.6f}")
print(f"Status: {'PASS' if result.passed else 'FAIL'}")
```

#### Thermodynamic Controller

```python
import networkx as nx
from runtime.thermo_controller import ThermoController

# Create system graph
graph = nx.DiGraph()
graph.add_edge("A", "B", type="covalent", latency_norm=0.4, coherency=0.9)
graph.nodes["A"]["cpu_norm"] = 0.5

# Initialize controller
controller = ThermoController(graph)

# Run control step
controller.control_step()

# Check system state
print(f"Free Energy: {controller.get_current_F():.6f}")
print(f"dF/dt: {controller.get_dF_dt():.6f}")
print(f"Circuit Breaker: {controller.circuit_breaker_active}")
```

#### API Endpoints

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

### CLI Tools

#### Energy Validation Script

```bash
# Validate metrics from command line
python scripts/validate_energy.py \
  --metric latency_p95=75.0 \
  --metric latency_p99=100.0 \
  --metric cpu_burn=0.65 \
  --verbose

# Validate from JSON file
python scripts/validate_energy.py metrics.json --output report.json

# Show configuration
python scripts/validate_energy.py --show-config
```

## Examples

Complete examples in `examples/`:
- `energy_validation_example.py`: Energy validator usage
- `thermo_hpc_ai_integration.py`: HPC-AI integration demo

## Testing

### Unit Tests

```bash
# Run energy validator tests
pytest tests/test_energy_validator.py -v

# Run all thermodynamics tests
pytest tests/test_thermo*.py -v
```

### Integration Tests

```bash
# Run integration tests
pytest tests/runtime/test_thermo_agent_bridge.py -v
pytest tests/sandbox/test_thermo_prototype.py -v
```

## Safety Features

### Formal Guarantees

1. **Monotonic Descent**: F_new ≤ F_old + ε (enforced by circuit breaker)
2. **Circuit Breaker**: Blocks unsafe mutations automatically
3. **Dual Approval**: Systemic actions require two engineer approvals
4. **Audit Trail**: Immutable 7-year decision log
5. **Recovery Window**: Temporary spikes allowed if expected to recover

### Observability

- **Real-time telemetry**: FastAPI endpoints
- **Prometheus metrics**: System free energy, dF/dt, violations
- **Audit logs**: JSONL format with full decision context
- **Export reports**: CI artifacts for compliance

## Operational Procedures

See [OPERATIONAL_RUNBOOK.md](./OPERATIONAL_RUNBOOK.md) for:
- Daily monitoring checklist
- Crisis response procedures
- Manual override protocols
- Troubleshooting guides
- Maintenance procedures
- Compliance reporting

## Compliance

### Regulatory Requirements

- **7-year audit retention**: All decisions logged
- **Dual approval**: Manual overrides require two signatures
- **Falsifiability**: System can be empirically validated
- **Continuous validation**: CI gates enforce energy limits

### Audit Logs

Location: `/var/log/tradepulse/thermo_audit.jsonl`

Format:
```json
{
  "ts": 1699999999.123,
  "F_old": 0.456,
  "F_new": 0.423,
  "dF_dt": -0.033,
  "crisis_mode": "normal",
  "topology_changes": [...],
  "action": "accepted"
}
```

## Performance

### Benchmarks

- **Control loop latency**: <1ms per step
- **Energy computation**: <100μs
- **GA evolution**: ~10ms (16 individuals, 10 generations)
- **Protocol activation**: <5s with fallbacks

### Scaling

- **Node count**: Tested up to 100 nodes
- **Edge count**: Tested up to 500 edges
- **History retention**: 10,000 telemetry records

## Troubleshooting

### High Free Energy (F > 1.30)

1. Check recent deployments
2. Verify metrics accuracy
3. Review bottleneck edge
4. Consider manual override if false positive

### Circuit Breaker Active

1. Do NOT override immediately
2. Investigate root cause
3. Verify metrics are correct
4. Obtain dual approval if needed

### Protocol Activation Failures

1. Check network connectivity
2. Verify protocol health (RDMA, CRDT, gRPC)
3. Review fallback chain execution
4. Check link activator logs

## References

### Papers

- Friston, K. (2010). The free-energy principle: a unified brain theory?
- Helmholtz, H. (1882). Die Thermodynamik chemischer Vorgänge

### Related Documentation

- [PATENTS.md](../../PATENTS.md): Patent filing for TACL
- [README.md](../../README.md): Main project README with TACL overview
- [HPC_AI_FINAL_REPORT.md](../../HPC_AI_FINAL_REPORT.md): HPC-AI integration

## Contributing

When contributing to TACL:

1. Maintain backward compatibility with existing metrics
2. Add comprehensive tests for new features
3. Update this documentation
4. Ensure CI validation passes
5. Follow monotonic descent principle

## License

See [LICENSE](../../LICENSE) for details.

## Contact

For questions or issues:
- Open a GitHub issue
- Tag `@thermodynamics` team
- Consult operational runbook for emergencies
