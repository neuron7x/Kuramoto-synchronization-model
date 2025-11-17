# Thermodynamics Metrics Formalization

## Overview

This document formalizes the mathematical foundations and computational procedures for the Thermodynamic Autonomic Control Layer (TACL) metrics system in TradePulse.

## Helmholtz Free Energy

The core metric in TACL is the Helmholtz free energy **F**, defined as:

```
F = U - T·S
```

Where:
- **F**: Free energy (dimensionless, target: F ≤ 1.35)
- **U**: Internal energy (system inefficiency penalties)
- **T**: Control temperature (fixed at 0.60 for TradePulse)
- **S**: Stability (entropy proportional to available headroom)

### Physical Interpretation

- **Low F**: System operates efficiently with ample headroom
- **High F**: System approaches instability, requires intervention
- **ΔF/Δt < 0**: Energy descent (desired, system improving)
- **ΔF/Δt > 0**: Energy ascent (warning, may trigger circuit breaker)

## Internal Energy (U)

Internal energy represents the aggregate penalty from system inefficiencies:

```
U = Σᵢ (wᵢ / W_total) · pᵢ
```

Where:
- **wᵢ**: Weight of metric i
- **W_total**: Sum of all weights (normalization factor)
- **pᵢ**: Penalty for metric i

### Penalty Computation

For each metric m with measured value **v** and threshold **τ**:

```
p(v, τ) = {
    0                    if v ≤ τ
    (v - τ) / τ         if v > τ
}
```

This represents the fractional excess above threshold.

## Stability (S)

Stability represents the system's available headroom:

```
S = (1/N) · Σᵢ max(0, hᵢ)
```

Where **hᵢ** is the headroom for metric i:

```
h(v, τ) = (τ - v) / τ
```

Properties:
- **h > 0**: Metric below threshold (headroom available)
- **h = 0**: Metric at threshold (no headroom)
- **h < 0**: Metric above threshold (penalty zone)

Only positive headroom contributes to stability.

## Monitored Metrics

### 1. Latency Metrics

#### latency_p95
- **Description**: 95th percentile end-to-end latency
- **Threshold**: 85.0 ms
- **Weight**: 1.6
- **Measurement**: Aggregated from service mesh telemetry
- **Formula**: P95(latency samples over 60s window)

#### latency_p99
- **Description**: 99th percentile end-to-end latency
- **Threshold**: 120.0 ms
- **Weight**: 1.9
- **Measurement**: Aggregated from service mesh telemetry
- **Formula**: P99(latency samples over 60s window)

### 2. Coherency Metrics

#### coherency_drift
- **Description**: Fractional drift of shared state across replicas
- **Threshold**: 0.08 (8%)
- **Weight**: 1.2
- **Measurement**: State divergence detector
- **Formula**: max_drift = max|sᵢ - s_ref| / |s_ref|

### 3. Resource Metrics

#### cpu_burn
- **Description**: CPU utilization ratio
- **Threshold**: 0.75 (75%)
- **Weight**: 0.9
- **Measurement**: Container metrics (cgroup stats)
- **Formula**: avg_cpu = mean(cpu_usage_per_core over 60s)

#### mem_cost
- **Description**: Memory footprint per node
- **Threshold**: 6.5 GiB
- **Weight**: 0.8
- **Measurement**: Container RSS + cache
- **Formula**: mem_total = RSS + page_cache - shared

### 4. Control Plane Metrics

#### queue_depth
- **Description**: Queue length at link activator ingress
- **Threshold**: 32.0 messages
- **Weight**: 0.7
- **Measurement**: Internal controller queue size
- **Formula**: queue_size = pending_activations + queued_mutations

#### packet_loss
- **Description**: Control-plane packet loss ratio
- **Threshold**: 0.005 (0.5%)
- **Weight**: 1.4
- **Measurement**: Gossip protocol statistics
- **Formula**: loss_ratio = dropped_messages / total_messages

## Monotonic Descent Constraint

### Tolerance Budget

The tolerance budget **ε** determines acceptable free energy increases:

```
ε = max(
    ε_min,
    ε_baseline · |F_baseline|,
    ε_adaptive · |dF/dt|
)
```

Where:
- **ε_min**: 1e-9 (numerical stability floor)
- **ε_baseline**: 0.01 (1% of baseline EMA)
- **ε_adaptive**: 0.5 (fraction of energy derivative)
- **F_baseline**: Exponential moving average of F

### Monotonicity Check

A topology change from state **F_old** to **F_new** passes if:

```
F_new ≤ F_old + ε
```

If this fails but **F_new > F_old**, the validator checks for expected recovery:

```
F_predicted(t+k) = F_new · decay^k + F_baseline · (1 - decay^k)
```

Where **decay** = 0.9 and **k** ∈ {1, 2, 3} (prediction window).

If **mean(F_predicted) < F_old**, the change is accepted as a temporary spike.

## Crisis Detection

### Crisis Modes

Three crisis modes based on free energy deviation:

```
mode = {
    NORMAL      if |F - F_baseline| < 0.10·F_baseline
    ELEVATED    if 0.10 ≤ |F - F_baseline| < 0.25·F_baseline
    CRITICAL    if |F - F_baseline| ≥ 0.25·F_baseline
}
```

### Latency Spike Detection

Latency spike ratio:

```
spike_ratio = avg_latency_current / avg_latency_baseline
```

Thresholds:
- **spike_ratio < 1.5**: Normal
- **1.5 ≤ spike_ratio < 2.0**: Elevated
- **spike_ratio ≥ 2.0**: Critical

### Energy Derivative

Rate of change:

```
dF/dt = (F_current - F_previous) / Δt
```

Triggers:
- **|dF/dt| > 0.01**: Warning
- **|dF/dt| > 0.05**: Critical

## Adaptive Recovery

### Recovery Agent Actions

The Q-learning recovery agent selects from three actions:

1. **slow**: Conservative recovery (small topology changes)
2. **medium**: Balanced recovery (moderate changes)
3. **fast**: Aggressive recovery (large changes)

### State Discretization

State **s = (F_deviation, latency_spike, crisis_duration)**:

- **F_deviation bins**: [0, 0.1), [0.1, 0.2), [0.2, 0.3), [0.3, 0.5), [0.5, ∞)
- **Latency spike bins**: [1.0, 1.5), [1.5, 2.0), [2.0, 3.0), [3.0, ∞)
- **Crisis duration bins**: [0, 5), [5, 10), [10, ∞) steps

### Reward Function

```
reward = -(F_new - F_old)
```

Positive reward for energy reduction, negative for increase.

### Q-Learning Update

```
Q(s, a) ← Q(s, a) + α · [r + γ · max_a' Q(s', a') - Q(s, a)]
```

Where:
- **α**: Learning rate (0.1)
- **γ**: Discount factor (0.95)
- **r**: Immediate reward
- **s'**: Next state

## Bond Evolution

### Genetic Algorithm

Population evolves bond types to minimize F:

```
fitness(topology) = -F(topology)
```

Parameters scale with crisis mode:

| Mode     | Population | Mutation Rate |
|----------|------------|---------------|
| NORMAL   | 16         | 0.6           |
| ELEVATED | 24         | 0.7           |
| CRITICAL | 32         | 0.8           |

### Selection

Tournament selection with size 3:
```
parent = best of {random_individual_1, random_individual_2, random_individual_3}
```

### Crossover

Single-point crossover with probability 0.4:
```
offspring = parent1[:k] + parent2[k:]
```

### Mutation

Uniform mutation (replace bond with random type):
```
mutate(bond) = random_bond_type() with probability p_mut
```

## Protocol Activation

### Bond-to-Protocol Mapping

Each bond type maps to a priority-ordered protocol list:

| Bond Type | Primary | Fallback | Last Resort |
|-----------|---------|----------|-------------|
| covalent  | RDMA    | CRDT     | Shared Mem  |
| ionic     | CRDT    | gRPC     | Shared Mem  |
| metallic  | Shared Mem | gRPC  | Local       |
| vdw       | gRPC    | Gossip   | Local       |
| hydrogen  | Gossip  | gRPC     | Local       |

### Activation Cost

Relative costs guide protocol selection:

- **RDMA**: 1.0 (highest cost, highest performance)
- **CRDT**: 0.8
- **Shared Memory**: 0.6
- **gRPC**: 0.4
- **Gossip**: 0.3
- **Local**: 0.1 (lowest cost, lowest performance)

### Fallback Chain

On activation failure:
1. Try primary protocol
2. If fails, try fallback
3. If fails, try last resort
4. If all fail, record activation failure and preserve old bond

## Telemetry and Observability

### Audit Log Format

Each control step logs a JSON record:

```json
{
  "ts": 1699999999.123,
  "F_old": 0.456,
  "F_new": 0.423,
  "dF_dt": -0.033,
  "epsilon": 0.0046,
  "crisis_mode": "normal",
  "circuit_breaker_active": false,
  "topology_changes": [
    {"src": "A", "dst": "B", "old": "vdw", "new": "covalent"}
  ],
  "action": "accepted"
}
```

### Prometheus Metrics

Exported metrics:

- **system_free_energy**: Current F value
- **system_dFdt**: Energy derivative
- **monotonic_violations_total**: Cumulative constraint violations
- **homeostasis_integrity_ratio**: CNS stabilizer health
- **stabilizer_phase_total**: Phase transitions counter
- **stabilizer_veto_events_total**: Hard veto decisions
- **tacl_delta_f**: Histogram of ΔF observations

## Validation Procedures

### Pre-Rollout Validation

Before production rollout:

1. Collect telemetry for 300s (5 minutes)
2. Compute F every 1s
3. Verify all F values ≤ 1.35
4. Check no sustained energy rise (> 5 steps)
5. Verify circuit breaker not triggered
6. Export validation report to `.ci_artifacts/energy_validation.json`

### Continuous Validation

During operation:

1. Monitor F in real-time via `/thermo/status` endpoint
2. Alert on F > 1.20 (warning threshold)
3. Trigger operator review on F > 1.30
4. Automatic rollback on F > 1.35 without dual approval

### Falsifiability Criteria

The system is considered falsified if:

1. **F > 1.35** sustained for > 10 steps without intervention
2. **Circuit breaker** fails to activate on unsafe mutations
3. **Monotonic violations** > 10 in 1 hour window
4. **Recovery agent** fails to reduce F within 50 steps of crisis onset

## References

- Friston, K. (2010). The free-energy principle: a unified brain theory?
- Helmholtz, H. (1882). Die Thermodynamik chemischer Vorgänge
- TradePulse TACL specification: `docs/TACL.md`
- Energy validator implementation: `runtime/energy_validator.py`
- Controller implementation: `runtime/thermo_controller.py`

## Revision History

| Version | Date       | Author | Changes |
|---------|------------|--------|---------|
| 1.0     | 2025-11-17 | Agent  | Complete formalization with all sections |
