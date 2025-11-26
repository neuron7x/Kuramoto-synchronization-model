# ADR 0002: Serotonin Controller - Hysteretic Hold Logic with SRE Observability

- **ADR ID:** ADR-0002
- **Status:** Accepted
- **Date:** 2025-11-17
- **Version:** 2.4.0
- **Decision Makers:** Principal Architect, SRE Guild, Neuromodulator Engineering Team

## Context / Architecturally Significant Requirement (ASR)

### Business Context

TradePulse operates in high-frequency trading environments where rapid market conditions can lead to:
- Excessive risk exposure during volatile periods
- Portfolio drawdowns from overtrading during stress
- Need for adaptive risk management that responds to chronic vs. acute stress

### Functional Requirements

The serotonin controller must:
1. Model tonic (chronic baseline) and phasic (acute spike) serotonin dynamics
2. Implement hysteretic hold logic to prevent trading during high-stress periods
3. Support desensitization mechanisms for chronic stress adaptation
4. Provide dynamic temperature floor adjustments for exploration control
5. Enable batch processing for backtesting and simulation

### Current Architecture

```
┌─────────────────────────────────────────────────┐
│         Serotonin Controller                    │
│                                                 │
│  ┌──────────┐    ┌──────────┐                 │
│  │  Tonic   │    │ Phasic   │                 │
│  │  Level   │    │ Level    │                 │
│  │  (EMA)   │    │  (EMA)   │                 │
│  └────┬─────┘    └────┬─────┘                 │
│       │               │                        │
│       └───────┬───────┘                        │
│               │                                │
│        ┌──────▼──────┐                        │
│        │ Combined    │                        │
│        │ Level       │                        │
│        └──────┬──────┘                        │
│               │                                │
│        ┌──────▼──────────┐                    │
│        │ Desensitization │                    │
│        │ Mechanism       │                    │
│        └──────┬──────────┘                    │
│               │                                │
│        ┌──────▼──────────┐                    │
│        │ Hysteretic      │                    │
│        │ Hold Logic      │                    │
│        └──────┬──────────┘                    │
│               │                                │
│               ▼                                │
│     Hold State + Floor                        │
└─────────────────────────────────────────────────┘
```

### NFR Priorities (ISO/IEC 25010)

1. **Reliability** (Availability, Fault Tolerance) - HIGH
2. **Performance Efficiency** (Time Behavior, Resource Utilization) - HIGH
3. **Maintainability** (Modularity, Testability) - MEDIUM
4. **Security** (Integrity, Accountability) - MEDIUM
5. **Usability** (Operability, Learnability) - MEDIUM

## Decision

We implement a **dual-component serotonin controller** with:

1. **Tonic/Phasic Separation:**
   - Tonic component (β=0.001-0.01): slow EMA for chronic stress baseline
   - Phasic component (β=0.1-0.3): fast EMA for acute transient events

2. **Hysteretic State Machine:**
   - Entry threshold: `stress_threshold + hysteresis/2`
   - Exit threshold: `release_threshold - hysteresis/2`
   - Prevents oscillation around threshold boundaries

3. **Cooldown Extension:**
   - Base cooldown period after exiting hold state
   - Extended cooldown if stress level remains elevated

4. **Desensitization Mechanism:**
   - Accumulates during prolonged high-stress periods
   - Reduces effective stress level by damping factor
   - Decays exponentially when stress subsides

5. **Performance Tracking (Optional):**
   - Step timing metrics
   - Hold state statistics
   - Throughput measurement

## Rationale

### Link to Utility Tree (ATAM)

| Quality Attribute | Scenario | Priority | Addressed By |
|------------------|----------|----------|--------------|
| **Reliability** | System must prevent trading during 99.9% of high-stress periods | H/H | Hysteretic hold logic with cooldown |
| **Performance** | Controller step() must complete in < 100μs for real-time operation | H/M | Optimized EMA calculations, optional perf tracking |
| **Maintainability** | New team members can understand logic within 30 minutes | M/M | Clear state machine, comprehensive docstrings |
| **Security** | State validation prevents corruption from invalid inputs | M/L | validate_state() method with bounds checking |

### Trade-Off Analysis

| Aspect | Simple Threshold | Hysteretic Controller (Chosen) | PID Controller |
|--------|------------------|--------------------------------|----------------|
| **Oscillation Prevention** | Poor - frequent flapping | Excellent - inherent stability | Good - requires tuning |
| **Computational Cost** | O(1) - minimal | O(1) - low overhead | O(1) but higher constants |
| **Tuning Complexity** | 1 parameter | 7-8 parameters | 3 parameters + wind-up logic |
| **Interpretability** | High | Medium-High | Low (derivative term) |
| **Physiological Basis** | None | Strong (matches neuroscience) | Weak |

**Sensitivity Point:** Hysteresis width directly affects hold duration stability. Values < 0.05 may cause flapping; values > 0.2 may reduce responsiveness.

**Risk:** Over-tuned desensitization could mask genuine risk signals during extended market stress.

### STPA: Unsafe Control Actions (UCA)

| Hazard | Source | UCA Type | Control Action | Context | Mitigation |
|--------|--------|----------|----------------|---------|------------|
| **H1: Trading during high volatility** | SerotoninController | Not Provided | Hold signal not activated | stress > threshold but hysteresis prevents entry | Asymmetric thresholds favor safety (enter easier than exit) |
| **H2: Stuck in hold during recovery** | SerotoninController | Stopped Too Soon | Hold released prematurely | Level drops briefly then spikes again | Cooldown period prevents immediate re-entry |
| **H3: Desensitization masking risk** | Desensitization Logic | Incorrect | Level damped too aggressively | Chronic stress > chronic_window | max_desensitization cap (0.8) preserves minimum sensitivity |
| **H4: State corruption from invalid input** | step() method | Incorrect | Invalid stress/drawdown values | NaN or negative inputs | Input validation, bounds clamping |

### NFR Mechanisms (ISO/IEC 25010)

#### Reliability
- **Fault Tolerance:** Input validation with clamping to valid ranges
- **Recoverability:** reset() method for clean state restoration
- **Availability:** No external dependencies, pure Python implementation

#### Performance Efficiency
- **Time Behavior:** O(1) step complexity, < 100μs on modern hardware
- **Resource Utilization:** Minimal memory footprint (~200 bytes state)
- **Batch Processing:** step_batch() for efficient historical analysis

#### Maintainability
- **Modularity:** Clear separation of concerns (tonic/phasic/hold/desensitization)
- **Testability:** Comprehensive test suite with 95%+ coverage
- **Analyzability:** get_state_summary() for debugging, validate_state() for invariant checking

#### Security
- **Integrity:** Immutable config (frozen dataclass), validated bounds
- **Accountability:** Structured logging via configurable logger callback

## Consequences

### Positive

1. **Reduced Drawdowns:** Hysteretic hold prevents overtrading during volatile periods
2. **Stable Behavior:** Cooldown mechanism eliminates threshold oscillation
3. **Adaptive Response:** Desensitization models real stress adaptation patterns
4. **Observability:** Built-in performance tracking and state validation
5. **Testing Efficiency:** Batch processing enables rapid backtesting

### Negative

1. **Tuning Complexity:** 8+ configuration parameters require careful calibration
2. **Technical Debt:** Need to migrate from YAML config to centralized config service
3. **Missing Metrics:** No automatic export to Prometheus/StatsD (manual logger injection)

### Technical Debt Items

| Item | Severity | Remediation |
|------|----------|-------------|
| YAML config coupling | Medium | Migrate to config service API (Q2 2025) |
| Manual logger injection | Low | Implement OpenTelemetry auto-instrumentation |
| Missing config validation UI | Low | Add to admin dashboard |

### SLO / Error Budget Impact

| SLI | Current SLO | Impact | Notes |
|-----|-------------|--------|-------|
| P95 step latency | < 500μs | **+50μs** | Acceptable - well within budget |
| Hold decision accuracy | > 99.5% | **+0.3%** | Improved - fewer false negatives |
| Config load failure rate | < 0.1% | **No change** | File-based, deterministic |

## DACI

- **Driver:** Principal Architect (Vasylenko Yaroslav)
- **Approver:** SRE Guild Lead, Risk Management
- **Contributors:** Neuromodulator Team, QA Engineering
- **Informed:** Trading Operations, Product Management

## Confidence Score

**Confidence: 4/5**

**Rationale:**
- Strong theoretical foundation (neuroscience-based model)
- Validated through extensive backtesting (1000+ scenarios)
- Proven in production on staging environments
- Minor uncertainty around optimal desensitization parameters for extreme events

**Human Review Recommended:**
- Quarterly review of desensitization parameters against actual market events
- Annual architecture review when market regimes shift significantly

## Implementation Roadmap

### Phase 1: Core Implementation (✅ Complete - v2.4.0)
- [x] Tonic/phasic separation with EMA dynamics
- [x] Hysteretic state machine with cooldown
- [x] Desensitization mechanism
- [x] Batch processing support
- [x] Performance tracking (optional)

### Phase 2: Enhanced Observability (Q1 2025)
- [ ] OpenTelemetry instrumentation
- [ ] Prometheus metrics exporter
- [ ] Grafana dashboard templates
- [ ] Alert rules for anomaly detection

### Phase 3: Production Hardening (Q2 2025)
- [ ] Config service integration
- [ ] A/B testing framework for parameter tuning
- [ ] Automated parameter optimization
- [ ] Chaos engineering test suite

### Phase 4: Advanced Features (Q3 2025)
- [ ] Multi-timeframe analysis
- [ ] Ensemble controllers
- [ ] Reinforcement learning for adaptive tuning

## Validation

### Test Coverage
- Unit tests: 95% coverage
- Integration tests: End-to-end workflow validation
- Property-based tests: Invariant checking (level bounds, monotonicity)
- Performance tests: Latency benchmarks

### Monitoring
- **Metrics:** `tacl.5ht.level`, `tacl.5ht.hold`, `tacl.5ht.cooldown`
- **Alerts:**
  - Level > 1.2 for > 5 minutes (warning)
  - Hold state > 30 minutes (investigate)
  - State validation failures (critical)

## References

1. [SEROTONIN_V2.4.0_SUMMARY.md](/SEROTONIN_V2.4.0_SUMMARY.md) - Implementation summary
2. [SEROTONIN_PRACTICAL_GUIDE.md](/docs/SEROTONIN_PRACTICAL_GUIDE.md) - Usage guide
3. [SEROTONIN_DEPLOYMENT_GUIDE.md](/docs/SEROTONIN_DEPLOYMENT_GUIDE.md) - Deployment procedures
4. NIST AI RMF - Risk management framework for AI components
5. ISO/IEC 25010:2023 - Quality model reference

## Related ADRs

- **ADR-0001:** Security, Compliance, and Documentation Automation (configuration governance)
- **ADR-0003:** [Planned] Neuromodulator Orchestration Framework

---

**Last Updated:** 2025-11-17
**Next Review:** 2026-02-17 (Quarterly)
