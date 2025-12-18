# RFC: Thermodynamic Autonomic Control Layer (TACL) Governance Specification

**Document Type**: RFC  
**Version**: 1.0.0  
**Status**: Draft  
**Author**: TradePulse Architecture Team  
**Date**: 2025-12-18  

---

## 1. Executive Summary

- **TACL is the governing brain of system stability** for TradePulse, not a feature — it enforces safety invariants across all autonomous adaptations
- **Monotonic Free Energy Descent** is the core safety guarantee: no autonomous change may increase system free energy F without explicit human approval
- The system implements **Helmholtz free energy** measurement: `F = U - T·S` where U is internal energy (weighted penalties), T is control temperature (0.60), and S is stability (headroom)
- **7-year audit trail** for all decisions, configuration changes, model versions, and regime switches is designed into the architecture
- **Dual approval** is required for systemic actions (A2 class) affecting topology or order flow
- **Circuit breaker** automatically halts unsafe mutations when sustained free energy increases are detected
- The specification is implemented and tested across `tacl/`, `runtime/`, and `evolution/` modules with CI gates validating energy bounds

---

## 2. System Boundary & Assumptions

### System Boundary

TACL governs the TradePulse distributed execution graph, operating at the layer between:
- **Above**: Trading strategies, execution algorithms, and user-facing APIs
- **Below**: Protocol layer (RDMA, CRDT, gRPC, shared memory), infrastructure, and market data feeds

### Explicit Assumptions

| Assumption | Verification Plan |
|------------|-------------------|
| Control temperature T=0.60 is optimal for TradePulse workloads | **Verification**: Run A/B test comparing T∈{0.4, 0.6, 0.8} on staging cluster; measure false positive circuit breaker activations |
| 7 metrics sufficiently characterize system health | **Verification**: Run principal component analysis on production telemetry; confirm >95% variance explained by current metric set |
| Genetic algorithm converges within 10 generations | **Verification**: Measure fitness plateau timing in `tests/evolution/test_crisis_ga.py` |
| Dual approval tokens expire after 1 hour | **Verification**: Operational audit showing no stale tokens used; implemented in `runtime/dual_approval.py` |

### Namespace Resolution

- **Authoritative namespace**: `tacl.*` and `runtime.*` for core TACL implementation
- `src/tradepulse.*` is the public API surface for risk controls
- Evidence: `pyproject.toml` declares `packages = ["tacl", "runtime", "core", "tradepulse"]`

---

## 3. Problem Statement

### What Fails Without TACL

| Condition | Failure Mode | Consequence |
|-----------|--------------|-------------|
| Uncontrolled autonomous adaptation | System may optimize itself into unstable states | Cascading failures, capital loss, regulatory breach |
| No monotonic descent constraint | Topology changes may increase latency/resource cost without bound | Service degradation, SLA violation |
| Missing audit trail | Unable to reconstruct decision rationale post-incident | Compliance failure (MiFID II, SEC Rule 15c3-5) |
| No human gate for systemic changes | AI/ML components may make irreversible changes | Unrecoverable state, trust loss |
| Protocol hotswap without guardrails | Incompatible protocol selection causes partition | Data loss, inconsistent state |

### When Failures Occur

- **Under high market volatility**: Regime changes stress the system; adaptation loops may race
- **During deployment windows**: New code may alter metric baselines unexpectedly
- **After infrastructure changes**: Network topology or hardware changes affect latency/coherency
- **Under attack scenarios**: Adversarial inputs may poison adaptation signals

---

## 4. Constraints & Invariants

### Global Invariants

| # | Invariant | Consequence if Violated | Enforcement Mechanism |
|---|-----------|------------------------|----------------------|
| I1 | **Safety**: No uncontrolled degradation | System enters unsafe state, capital at risk | Circuit breaker, kill switch, monotonic descent gate |
| I2 | **Auditability**: 7-year decision trail | Regulatory non-compliance, litigation exposure | Append-only JSONL logs, signed entries |
| I3 | **Resource Governance**: F is first-class | Resource exhaustion, latency spikes | Free energy validation, CI gates |
| I4 | **Reproducibility**: Deterministic replay | Unable to debug incidents | Versioned configs, seeded RNG |
| I5 | **Event-based Sparsity**: Compute on trigger | Always-on overhead exhausts budget | Event-driven control loop, circadian gating |
| I6 | **Trading Domain**: Capital preservation dominates | Catastrophic loss | Kill switch, risk limits, pre-trade checks |

### Formal Constraints

1. **Monotonic Free Energy Descent**:
   ```
   ∀ t: F(t+1) ≤ F(t) + ε(t)
   ```
   Where `ε(t) = max(1e-9, 0.01 * baseline_EMA(t), 0.05 * |dF/dt(t)|)`

2. **Action Classification Constraint**:
   - A0 (Observation): Always permitted
   - A1 (Local Correction): Permitted in NORMAL, DEGRADED states
   - A2 (Systemic): Requires dual approval; blocked in CRISIS

3. **Energy Envelope**:
   ```
   rest_potential ≤ F ≤ action_potential
   1.0 ≤ F ≤ 1.35
   ```

**Evidence anchors:** `tacl/behavioral_contract.py: BehavioralContract`, `runtime/behavior_contract.py: tacl_gate`, `runtime/thermo_controller.py: _check_monotonic_with_tolerance`

---

## 5. Design Hypotheses

| Hypothesis | Conditions | Necessary Outcome |
|------------|------------|-------------------|
| If latency_p95 > 85ms AND latency_p99 > 120ms | System under load stress | Elevated crisis mode triggers GA with larger population |
| If F increases for 5 consecutive steps | Sustained degradation | Circuit breaker activates, blocking all topology mutations |
| If action_class = A2 AND dual_approved = false | Systemic change attempted without approval | TACL gate rejects with `dual_approval_missing` |
| If kill_switch active | External or internal safety signal | All control loop actions blocked; state recorded |
| If coherency_drift > 0.08 | Distributed state divergence | Increased penalty weight, recovery agent engaged |

---

## 6. Mechanism Specifications

### 6.1 Free Energy Measurement

**Purpose**: Quantify system health as a single scalar for optimization and gating decisions.

**Formula**:
```
F = U - T·S

Where:
  U = base_internal_energy + Σᵢ (wᵢ · penalty(metricᵢ)) / Σᵢ wᵢ
  S = max(entropy_floor, Σᵢ (wᵢ · stability(metricᵢ)) / Σᵢ wᵢ)
  T = 0.60 (control temperature)
```

**Inputs**:
| Metric | Threshold | Weight | Unit |
|--------|-----------|--------|------|
| latency_p95 | 85.0 | 1.6 | ms |
| latency_p99 | 120.0 | 1.9 | ms |
| coherency_drift | 0.08 | 1.2 | ratio |
| cpu_burn | 0.75 | 0.9 | ratio |
| mem_cost | 6.5 | 0.8 | GiB |
| queue_depth | 32.0 | 0.7 | messages |
| packet_loss | 0.005 | 1.4 | ratio |

**Outputs**: `EnergyValidationResult(passed, free_energy, internal_energy, entropy, penalties, reason)`

**Update Rule**: Computed on every control step (1ms cadence in production, configurable)

**Metrics**:
- `system_free_energy` (Prometheus gauge)
- `system_dFdt` (Prometheus gauge)
- `tacl_delta_f` (Prometheus histogram)

**Failure Modes**:
| Failure | Detection | Safeguard |
|---------|-----------|-----------|
| Metric collection timeout | Telemetry staleness counter | Use last-known values with decay |
| Metric values out of range | Validation checks | Clamp to bounds, log warning |
| Division by zero (weight sum) | Initialization validation | Raise ValueError at construction |

**Evidence anchors:** `tacl/energy_model.py: EnergyModel`, `tacl/energy_model.py: DEFAULT_THRESHOLDS`, `tacl/energy_model.py: DEFAULT_WEIGHTS`, `config/thermo_config.yaml`, `tests/test_energy_validator.py`

---

### 6.2 Stress Detection & Regime Control

**Purpose**: Classify system state and adjust control aggressiveness accordingly.

**Inputs**: Current F, baseline F, dF/dt

**Outputs**: `CrisisMode ∈ {NORMAL, ELEVATED, CRITICAL}`

**Update Rule**:
```python
def detect(F_current, F_baseline, threshold):
    deviation = (F_current - F_baseline) / max(F_baseline, 1e-9)
    if deviation >= 0.25:
        return CrisisMode.CRITICAL
    elif deviation >= 0.10:
        return CrisisMode.ELEVATED
    else:
        return CrisisMode.NORMAL
```

**Hysteresis**: Mode changes require 3 consecutive samples to prevent oscillation

**Threat Contours**:
| Contour | dF/dt Threshold | Action |
|---------|-----------------|--------|
| Green | |dF/dt| < 0.01 | Normal operation |
| Yellow | 0.01 ≤ |dF/dt| < 0.05 | Increase sampling, alert operators |
| Red | |dF/dt| ≥ 0.05 | Engage recovery agent, consider circuit breaker |

**Safe-Mode Policy**: In CRITICAL, block A2 actions; downgrade to A1 maximum

**Evidence anchors:** `evolution/crisis_ga.py: CrisisMode`, `runtime/thermo_controller.py: control_step`, `config/thermo_config.yaml: crisis`

---

### 6.3 Evolutionary Reconfiguration (GA/RL)

**Purpose**: Optimize system topology using genetic algorithm with crisis-aware scaling.

**When Allowed**:
- System not in CRITICAL mode
- Circuit breaker not active
- Proposed topology satisfies monotonic descent

**Constraints**:
- Population size scales with crisis: 16 (normal) → 24 (elevated) → 32 (critical)
- Mutation probability scales: 0.6 → 0.7 → 0.8
- Elitism preserves 2 best individuals per generation

**Rollback Logic**:
1. Store current topology hash before evolution
2. Apply new topology via LinkActivator
3. If activation fails, revert to previous bond types
4. Log rollback event to audit trail

**Human Gate**: A2 systemic changes require `THERMO_DUAL_TOKEN` environment variable set with valid dual-approval token

**Evidence anchors:** `evolution/crisis_ga.py: CrisisAwareGA`, `evolution/bond_evolver.py: evolve_bonds`, `runtime/thermo_controller.py: _handle_crisis`, `runtime/dual_approval.py`

---

### 6.4 Protocol Hot-Swap Policy

**Purpose**: Dynamically select optimal communication protocol for each link.

**Protocols** (in priority order):
1. RDMA — Lowest latency, highest resource cost
2. Shared Memory — For co-located processes
3. CRDT — For eventually consistent state sync
4. gRPC — General-purpose fallback
5. Gossip — For large-scale broadcast

**Admissibility Rules**:
| Protocol | Condition |
|----------|-----------|
| RDMA | Network supports RDMA; latency_p95 < 10ms required |
| Shared Memory | Processes on same host |
| CRDT | Coherency requirements allow eventual consistency |
| gRPC | Default fallback; always available |
| Gossip | Node count > 10; broadcast pattern detected |

**Guardrails**:
- Maximum 3 retry attempts per activation
- 5-second timeout per protocol activation
- Fallback chain: RDMA → gRPC → Gossip

**Rollback**: If new protocol fails verification ping, immediately revert to previous

**Human Approval**: Protocol changes are A1 (local correction); no dual approval required unless affecting >50% of links

**Evidence anchors:** `runtime/link_activator.py: LinkActivator`, `config/thermo_config.yaml: link_activator`, `runtime/thermo_controller.py: _apply_topology_changes`

---

### 6.5 Telemetry & API Exposure

**Endpoints** (FastAPI):
| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/thermo/status` | GET | Current system state | Read |
| `/thermo/history` | GET | Historical telemetry | Read |
| `/thermo/crisis` | GET | Crisis statistics | Read |
| `/thermo/activations` | GET | Protocol activation log | Read |
| `/thermo/override` | POST | Manual override | Write + Dual Approval |

**Cadence**: Telemetry exported every 60 seconds to `.ci_artifacts/`

**Roles/Permissions**:
- `thermo:read` — View telemetry, history, status
- `thermo:write` — Trigger manual override (requires dual approval)
- `thermo:admin` — Deactivate kill switch, modify configuration

**Redlines** (alerts trigger):
- F > 1.30 (warning)
- F > 1.35 (critical, rollback triggered)
- dF/dt > 0.05 (rate alert)
- Circuit breaker active (incident opened)

**Evidence anchors:** `runtime/thermo_api.py`, `observability/dashboards/tradepulse-risk-engine.json`, `monitoring/grafana/risk_dashboard.json`

---

### 6.6 CI Safety Gates

**Energy Validation Gate** (required before deploy):
```yaml
# .github/workflows/thermo-evolution.yml
- name: Run stability tests
  run: pytest -q tests/test_energy.py -m stability
- name: Benchmark bonds / ensure ΔF improvement
  run: python scripts/benchmark_bonds.py --target-dF 1e-10
- name: Enforce thermodynamic monotonicity
  run: pytest -m monotonic -q
```

**What Must Pass**:
1. Stability tests: F ≤ 1.35 for nominal scenarios
2. Monotonicity gate: No violations in controlled tests
3. Bond benchmark: ΔF improvement target met
4. Degradation scenarios: Must fail validation (negative tests)

**Gate Artifacts**:
- `.ci_artifacts/energy_validation.json`
- `.ci_artifacts/release_gates.json`

**Evidence anchors:** `.github/workflows/thermo-evolution.yml`, `tacl/validate.py`, `tacl/release_gates.py`, `tests/tacl/test_validate_energy.py`, `scripts/benchmark_bonds.py`

---

### 6.7 Audit Trail

**Format**: JSONL (append-only)

**Location**: `/var/log/tradepulse/thermo_audit.jsonl`

**Schema**:
```json
{
  "ts": 1699999999.123,
  "F_old": 0.456,
  "F_new": 0.423,
  "dF_dt": -0.033,
  "epsilon": 0.0045,
  "crisis_mode": "NORMAL",
  "circuit_breaker_active": false,
  "topology_changes": [
    {"src": "A", "dst": "B", "old": "vdw", "new": "covalent"}
  ],
  "manual_override": false,
  "override_reason": "",
  "action": "accepted"
}
```

**Retention**: 7 years (configurable via `telemetry.audit_retention_years`)

**Provenance**: Each entry includes:
- Timestamp (UTC)
- Topology hash (SHA-256)
- Configuration version
- Model version (if applicable)

**Verification**: Logs are append-only; integrity verified by checksum chain

**Evidence anchors:** `runtime/thermo_controller.py: AUDIT_LOG_PATH`, `runtime/thermo_controller.py: _record_telemetry`, `observability/audit/trail.py: AuditTrail`

---

## 7. Interfaces & Contracts

### Python API

```python
from tacl.energy_model import EnergyValidator, EnergyMetrics

validator = EnergyValidator(max_free_energy=1.35)
metrics = EnergyMetrics(
    latency_p95=75.0,
    latency_p99=100.0,
    coherency_drift=0.05,
    cpu_burn=0.65,
    mem_cost=5.5,
    queue_depth=25.0,
    packet_loss=0.003,
)
result = validator.evaluate(metrics)
assert result.passed
```

### Behavioral Contract API

```python
from tacl.behavioral_contract import BehavioralContract

contract = BehavioralContract(
    rest_potential=1.0,
    action_potential=1.35,
    monotonic_tolerance=5e-3,
    required_approvals=frozenset({"operations", "safety"}),
)
report = contract.enforce(results_sequence, approvals=["operations", "safety"])
assert report.compliant
```

### Schema Versioning

- Configuration schema: `config/thermo_config.yaml` (v1.0)
- Telemetry schema: `observability/schemas/thermo_telemetry.json` (v1.0)
- API schema: OpenAPI 3.0 at `/thermo/openapi.json`

### SLAs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Control loop latency | < 1ms p99 | Histogram at `tacl_control_loop_duration_seconds` |
| Energy computation | < 100μs | Sampled in tests |
| API response time | < 50ms p95 | Prometheus `http_request_duration_seconds` |

**Evidence anchors:** `tacl/energy_model.py: EnergyValidator`, `tacl/behavioral_contract.py: BehavioralContract`, `config/thermo_config.yaml`

---

## 8. Protocol Hot-Swap Policy

### Admissibility Matrix

| From Protocol | To Protocol | Condition | Guardrail |
|---------------|-------------|-----------|-----------|
| Any | RDMA | Hardware supports; latency_p95 < 10ms | Ping verification required |
| Any | Shared Memory | Same host | Process affinity check |
| Any | CRDT | coherency_drift tolerance > 0.1 | Eventual consistency acceptable |
| Any | gRPC | Always | Default fallback |
| Any | Gossip | node_count > 10 | Fan-out verification |

### Rollback Triggers

1. Activation timeout (5s)
2. Verification ping failure
3. Immediate latency spike > 2x baseline
4. Coherency violation within 10s of activation

### Human Approval Rules

- Single-link protocol change: A1 (no approval needed)
- Multi-link (>50% of graph): A2 (dual approval required)
- Emergency fallback to gRPC: Automatic (logged for audit)

**Evidence anchors:** `runtime/link_activator.py`, `config/thermo_config.yaml: link_activator`

---

## 9. Safety Model

### Monotonic Free Energy Descent Formalization

**Theorem**: Under TACL governance, system free energy F is non-increasing over time (within tolerance ε) unless human override is granted.

**Pseudocode**:
```python
def tacl_gate(action_class, F_now, F_next, epsilon, dual_approved):
    # I1: Kill switch overrides all
    if is_kill_switch_active():
        return Decision(allowed=False, reason="kill_switch_active")
    
    # I2: Check action classification
    if action_class == A2 and not dual_approved:
        return Decision(allowed=False, reason="dual_approval_missing")
    
    # I3: Enforce monotonic descent
    if F_next > F_now + epsilon:
        return Decision(allowed=False, reason="free_energy_spike")
    
    # I4: Check recovery path for temporary spikes
    if F_next > F_now and not recovery_predicted(F_next, window=3):
        return Decision(allowed=False, reason="no_recovery_path")
    
    return Decision(allowed=True, reason="allowed")
```

### Gating Logic

```
┌─────────────────────────────────────────────────────────────┐
│                      TACL Gate                               │
├─────────────────────────────────────────────────────────────┤
│  Input: (module, action_class, F_now, F_next, epsilon)      │
│                                                             │
│  ┌─────────────────┐                                        │
│  │ Kill Switch?    │──Yes──► REJECT: kill_switch_active     │
│  └────────┬────────┘                                        │
│           │ No                                              │
│  ┌────────▼────────┐                                        │
│  │ Action in       │──No───► REJECT: action_not_allowed     │
│  │ mandate?        │                                        │
│  └────────┬────────┘                                        │
│           │ Yes                                             │
│  ┌────────▼────────┐                                        │
│  │ A2 && !approved?│──Yes──► REJECT: dual_approval_missing  │
│  └────────┬────────┘                                        │
│           │ No                                              │
│  ┌────────▼────────┐                                        │
│  │ F_next > F_now  │──Yes──┐                                │
│  │ + epsilon?      │       │                                │
│  └────────┬────────┘       │                                │
│           │ No             │                                │
│           │       ┌────────▼────────┐                       │
│           │       │ Recovery path?  │──No──► REJECT         │
│           │       └────────┬────────┘                       │
│           │                │ Yes                            │
│           │                ▼                                │
│           └───────────────►  ALLOW                          │
└─────────────────────────────────────────────────────────────┘
```

**Evidence anchors:** `runtime/behavior_contract.py: tacl_gate`, `runtime/thermo_controller.py: control_step`

---

## 10. Rejected Alternatives

| Alternative | Invariant Violated | Reason |
|-------------|-------------------|--------|
| **Simple threshold alerting** | I3 (Resource Governance) | No optimization feedback loop; reactive only |
| **Unconstrained RL optimization** | I1 (Safety) | RL may explore unsafe regions; no monotonic guarantee |
| **Manual-only topology changes** | I5 (Event-based Sparsity) | Latency of human intervention incompatible with ms-scale control |
| **Single-approval for A2** | I2 (Auditability) | Insufficient accountability for systemic changes |
| **Fixed protocol selection** | I3 (Resource Governance) | Cannot adapt to changing network conditions |

---

## 11. Verification & Falsifiability

### Tests That Can Disprove TACL Claims

| Claim | Test | Expected Outcome | Test File |
|-------|------|------------------|-----------|
| Monotonic descent enforced | Inject F increase > ε | Circuit breaker activates | `tests/runtime/test_thermo_controller.py` |
| Energy computation normalized | Set all metrics to threshold | F ≈ 1.0 | `tests/test_energy_validator.py` |
| Dual approval required for A2 | Attempt A2 without token | Gate rejects | `tests/runtime/test_behavior_contract.py` |
| GA converges in 10 generations | Run GA with random population | Fitness plateau reached | `tests/evolution/test_crisis_ga.py` |
| Kill switch halts all actions | Activate kill switch, attempt control step | No topology changes | `tests/runtime/test_kill_switch_controller.py` |

### Experiments to Validate

1. **Chaos engineering**: Inject random metric spikes; verify circuit breaker engages
2. **Long-running soak test**: Run 1M control steps; verify no memory leak, no monotonic violations
3. **Protocol failure simulation**: Kill RDMA mid-operation; verify fallback to gRPC

**Evidence anchors:** `tests/test_energy_validator.py`, `tests/tacl/test_validate_energy.py`, `tests/runtime/test_kill_switch_controller.py`

---

## 12. Observability

### Prometheus Metrics

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `system_free_energy` | Gauge | — | Current F value |
| `system_dFdt` | Gauge | — | Rate of change |
| `tacl_delta_f` | Histogram | — | Distribution of ΔF |
| `homeostasis_integrity_ratio` | Gauge | — | CNS stabilizer health |
| `stabilizer_phase_total` | Counter | phase | Phase transitions |
| `stabilizer_veto_events_total` | Counter | type | Veto decisions |
| `monotonic_violations_total` | Counter | — | Safety violations |

### Logs

- **Location**: `/var/log/tradepulse/thermo_audit.jsonl`
- **Format**: JSONL with structured fields
- **Rotation**: Daily, compressed after 7 days
- **Retention**: 7 years

### Traces

- OpenTelemetry integration via `observability/tracing/`
- Span: `tacl.control_step` with attributes for F, dF/dt, crisis_mode
- Trace ID propagated through protocol activations

### Redlines (Alert Thresholds)

| Condition | Severity | Action |
|-----------|----------|--------|
| F > 1.30 | Warning | Page on-call |
| F > 1.35 | Critical | Rollback triggered, incident opened |
| Circuit breaker active > 5 min | Critical | Escalate to platform lead |
| Audit log write failure | Critical | Halt system, manual intervention |

**Evidence anchors:** `runtime/thermo_controller.py: _init_homeostasis_metrics`, `observability/dashboards/tradepulse-risk-engine.json`

---

## 13. Audit Trail & Governance

### Retention Policy

| Data Type | Retention | Storage |
|-----------|-----------|---------|
| Decision logs | 7 years | S3 Glacier Deep Archive |
| Configuration versions | 7 years | Git history + S3 |
| Model versions | 7 years | Model registry with checksums |
| Telemetry snapshots | 90 days hot, 7 years cold | Prometheus → S3 |

### Provenance Requirements

Each decision record includes:
- Timestamp (ISO 8601 UTC)
- Topology hash (SHA-256)
- Configuration git SHA
- Model version (if applicable)
- Operator identity (for overrides)

### Change Control

1. Configuration changes require PR review
2. Threshold changes require A2 approval (dual signature)
3. Emergency overrides logged with full context
4. All changes trigger CI validation

**Evidence anchors:** `observability/audit/trail.py: AuditTrail`, `runtime/thermo_controller.py: _record_telemetry`, `core/security/integrity.py: IntegrityVerifier`

---

## 14. Rollout Plan

### Phase 1: Canary (Week 1)
- Deploy to 5% of staging traffic
- Monitor: F distribution, false positive rate
- Kill switch test: Verify activation works
- Gate: No circuit breaker activations from false positives

### Phase 2: Staging Full (Week 2)
- Deploy to 100% staging
- Run soak test (72 hours continuous)
- Verify audit log integrity
- Gate: F < 1.35 for 99.9% of samples

### Phase 3: Production Canary (Week 3)
- Deploy to 1% production traffic
- Human monitoring required
- Rollback trigger: Any F > 1.40

### Phase 4: Production Full (Week 4+)
- Gradual ramp: 1% → 10% → 50% → 100%
- Each stage: 24-hour soak minimum
- Final gate: 7-day stability with no manual overrides

### Rollback Triggers

- F > 1.40 for > 60 seconds
- Circuit breaker active for > 10 minutes without resolution
- Audit log write failures
- Operator manual trigger

**Evidence anchors:** `docs/thermodynamics/OPERATIONAL_RUNBOOK.md`, `tacl/release_gates.py`

---

## 15. Open Questions

| Question | Owner | Next Experiment |
|----------|-------|-----------------|
| Optimal control temperature T for different market regimes | @thermo-team | A/B test T∈{0.4, 0.6, 0.8} with synthetic volatility |
| Should coherency_drift threshold vary by asset class? | @markets-team | Analyze per-asset drift distributions in production |
| Can GA population size be reduced without quality loss? | @evolution-team | Ablation study on pop_size ∈ {8, 16, 24, 32} |
| RDMA protocol availability in cloud environments | @infra-team | Survey AWS/GCP/Azure RDMA support matrix |
| Audit log tamper-proofing via blockchain | @security-team | POC with Hyperledger Fabric for log anchoring |

---

## Decision Record

**Decision**: Adopt TACL as the mandatory governance layer for all autonomous adaptations in TradePulse

**Alternatives**:
1. Simple threshold alerting — Rejected: no optimization loop
2. Unconstrained RL — Rejected: safety not guaranteed
3. Manual-only changes — Rejected: latency incompatible with ms-scale trading

**Invariants Affected**: All global invariants (I1-I6)

**Evidence**: 
- `tacl/` module implementation (energy_model.py, behavioral_contract.py)
- `runtime/thermo_controller.py` with 1400+ lines of control logic
- `tests/test_energy_validator.py` with 20+ test cases
- CI gate at `.github/workflows/ci.yml`

**Risk**: 
- False positive circuit breaker activations may halt legitimate trading
- Mitigation: Tunable tolerance budgets, manual override capability

**Rollback**: 
- Set `TACL_ENABLED=false` environment variable
- Fallback to static configuration without adaptive optimization

**Verification**:
- `pytest tests/test_energy_validator.py tests/tacl/ -v`
- `pytest -q tests/test_energy.py -m stability`
- `python scripts/benchmark_bonds.py --target-dF 1e-10`
- Production monitoring via Prometheus/Grafana

---

## Appendix A: Evidence Map

| Claim | Invariant | Artifact | Path/Test |
|-------|-----------|----------|-----------|
| Free energy computed correctly | I3 | EnergyModel class | `tacl/energy_model.py` |
| Monotonic descent enforced | I1 | tacl_gate function | `runtime/behavior_contract.py` |
| Circuit breaker activates on violations | I1 | ThermoController | `runtime/thermo_controller.py:control_step` |
| Dual approval required for A2 | I2 | DualApprovalManager | `runtime/dual_approval.py` |
| Kill switch halts operations | I6 | KillSwitchManager | `runtime/kill_switch.py` |
| Audit trail persisted | I2 | AuditTrail class | `observability/audit/trail.py` |
| Protocol hot-swap with fallback | I3 | LinkActivator | `runtime/link_activator.py` |
| GA scales with crisis mode | I1 | CrisisAwareGA | `evolution/crisis_ga.py` |
| CI validates energy bounds | I4 | thermo-evolution.yml | `.github/workflows/thermo-evolution.yml`, `tacl/validate.py` |
| Idempotency for API | I4 | IdempotencyCache | `application/api/idempotency.py` |
| Integrity verification | I2 | IntegrityVerifier | `core/security/integrity.py` |
| 7-year retention configured | I2 | Config | `config/thermo_config.yaml` |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Free Energy (F)** | Scalar measure of system inefficiency; computed as F = U - T·S |
| **Internal Energy (U)** | Weighted sum of metric penalties plus base energy |
| **Entropy (S)** | Measure of system slack/headroom relative to thresholds |
| **Control Temperature (T)** | Discount factor for entropy; fixed at 0.60 |
| **Monotonic Descent** | Constraint that F(t+1) ≤ F(t) + ε for all autonomous changes |
| **Circuit Breaker** | Safety mechanism that blocks topology mutations on sustained F increase |
| **Kill Switch** | Emergency halt for all trading and control loop operations |
| **A0/A1/A2 Actions** | Classification: Observation / Local Correction / Systemic Change |
| **Dual Approval** | Requirement for two independent operator signatures for A2 actions |
| **Crisis Mode** | System state: NORMAL / ELEVATED / CRITICAL based on F deviation |
| **TACL Gate** | Decision function that approves or rejects proposed actions |
| **Behavioral Contract** | Formal specification of allowed system behaviors |
| **Link Activator** | Component managing protocol hot-swapping |
| **Recovery Agent** | Q-learning agent that selects recovery strategies |
| **Crisis GA** | Genetic algorithm with crisis-aware population scaling |
| **Baseline EMA** | Exponential moving average of historical F values |
| **Tolerance Budget (ε)** | Maximum allowed F increase for monotonic descent |
| **Rest Potential** | Lower bound of acceptable F (1.0) |
| **Action Potential** | Upper bound triggering rollback (1.35) |
| **RDMA** | Remote Direct Memory Access — low-latency protocol |
| **CRDT** | Conflict-free Replicated Data Type — eventual consistency |
| **CNS Stabilizer** | Central Nervous System stabilizer for signal processing |
| **VLPO Filter** | Ventrolateral preoptic filter for outlier suppression |
| **Telemetry** | System metrics collected for observability |

---

*Document generated following TradePulse Documentation Architecture v1.1*
