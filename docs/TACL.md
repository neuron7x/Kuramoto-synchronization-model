# Thermodynamic Autonomic Control Layer (TACL)

The Thermodynamic Autonomic Control Layer is responsible for validating that the
TradePulse execution graph operates inside the safe energy envelope before a
rollout progresses beyond the laboratory environment.  The validator ingests a
compact set of telemetry collected from the link activator and control plane and
computes the Helmholtz free energy (Helmholtz definition and variational framing supported by [@Callen1985Thermodynamics; @Friston2010FreeEnergy])

\[
F = U - T S
\]

where:

- **U** is the internal energy composed of weighted penalties derived from the
  latency, coherency, and resource metrics.
- **T** is the control temperature (fixed to 0.60 for TradePulse) representing
  how aggressively we discount available slack.
- **S** is the stability term, proportional to the headroom each metric keeps
  relative to its threshold.  Higher stability increases entropy and therefore
  reduces the free energy.

## Metrics and Thresholds

| Metric            | Description                              | Threshold | Weight |
| ----------------- | ---------------------------------------- | --------- | ------ |
| `latency_p95`     | 95th percentile end-to-end latency (ms)  | 85.0      | 1.6    |
| `latency_p99`     | 99th percentile end-to-end latency (ms)  | 120.0     | 1.9    |
| `coherency_drift` | Fractional drift of shared state         | 0.08      | 1.2    |
| `cpu_burn`        | CPU utilisation ratio (0–1)              | 0.75      | 0.9    |
| `mem_cost`        | Memory footprint per node (GiB)          | 6.5       | 0.8    |
| `queue_depth`     | Queue length at the activator ingress    | 32.0      | 0.7    |
| `packet_loss`     | Control-plane packet loss ratio (0–1)    | 0.005     | 1.4    |

The validator normalises penalties by the sum of weights before combining them
with the base internal energy.  This behaviour fixes the regression that caused
`validate-energy` to fail after merge: previously the penalties were summed
without normalisation which doubled the influence of latency and packet loss
metrics.

## Acceptable Energy Range

The CI pipeline declares success when the computed free energy does not exceed
**1.35**.  This boundary was derived from the post-incident review and gives a
12% safety margin relative to the highest energy observed during the hot path
load tests.

- Free energy ≤ 1.35: rollout proceeds to release gates.
- Free energy > 1.35: automated rollback is triggered.

## Authorisations for Energy Exceptions

Temporary exceptions to the energy budget require dual approval:

1. **Thermodynamic Duty Officer** (rotating weekly).
2. **Platform Staff Engineer** responsible for the affected cluster.

Both approvals must be recorded in the release ticket together with the
telemetry snapshots exported by `.ci_artifacts/energy_validation.json`.

## Programmatic Implementation

The TACL specification described in this document is implemented in the following modules:

### Core Modules

- **`runtime/energy_validator.py`**: Implements the energy validation logic
  - Computes Helmholtz free energy: F = U - T·S
  - Validates metrics against thresholds
  - Exports validation reports to JSON
  
- **`runtime/thermo_config.py`**: Centralized configuration for all TACL components
  - Crisis thresholds and detection parameters
  - Safety constraints (monotonic descent, circuit breaker)
  - Genetic algorithm and recovery agent configuration
  - Load from YAML or environment variables

- **`runtime/thermo_controller.py`**: Main control loop orchestrator
  - Orchestrates thermodynamic control steps
  - Enforces monotonic descent constraint
  - Manages crisis detection and recovery
  - Integrates CNS stabilizer, recovery agent, and GA

- **`runtime/thermo_api.py`**: FastAPI telemetry endpoints
  - `/thermo/status` - Current system state
  - `/thermo/history` - Historical telemetry
  - `/thermo/crisis` - Crisis statistics
  - `/thermo/activations` - Protocol activation history
  - `/thermo/override` - Manual override endpoint

### Configuration

Default configuration is provided in `config/thermo_config.yaml` with all metrics,
thresholds, and control parameters matching this specification.

### CLI Tools

**Energy Validation Script** (`scripts/validate_energy.py`):
```bash
# Validate metrics from command line
python scripts/validate_energy.py \
  --metric latency_p95=75.0 \
  --metric latency_p99=100.0 \
  --metric cpu_burn=0.65 \
  --output validation_report.json

# Validate from JSON file
python scripts/validate_energy.py metrics.json --verbose

# Show current configuration
python scripts/validate_energy.py --show-config
```

### Usage Example

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

# Export validation report
validator.export_validation_report(Path(".ci_artifacts/energy_validation.json"))
```

### Documentation

For comprehensive documentation, see:

- **[Thermodynamics Documentation Hub](./thermodynamics/README.md)**: Complete guide
- **[Metrics Formalization](./thermodynamics/METRICS_FORMALIZATION.md)**: Mathematical foundations
- **[Operational Runbook](./thermodynamics/OPERATIONAL_RUNBOOK.md)**: Production procedures
- **[Energy Validation Example](../examples/energy_validation_example.py)**: Usage examples

### Testing

Comprehensive test suite in `tests/test_energy_validator.py`:
```bash
pytest tests/test_energy_validator.py -v
```
