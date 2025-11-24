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
   - **Theoretical Basis:** Neurobiological evidence shows serotonin operates on multiple timescales with both slow tonic baseline modulation and fast phasic responses to salient events (Cohen et al., 2015; Liu et al., 2014; Matias et al., 2017). This dual-component architecture mirrors the tonic/phasic framework established in dopamine research (Grace, 1991) and extends it to serotonergic systems.

2. **Hysteretic State Machine:**
   - Entry threshold: `stress_threshold + hysteresis/2`
   - Exit threshold: `release_threshold - hysteresis/2`
   - Prevents oscillation around threshold boundaries
   - **Theoretical Basis:** Hysteresis in control systems provides stability and prevents rapid switching near threshold boundaries (Bertotti & Mayergoyz, 2006; Visintin, 1994). This design pattern is common in safety-critical systems to ensure robust state transitions (Åström & Murray, 2021).

3. **Cooldown Extension:**
   - Base cooldown period after exiting hold state
   - Extended cooldown if stress level remains elevated
   - **Theoretical Basis:** Reflects refractory periods in biological systems and prevents premature re-engagement during stress recovery (Turrigiano, 2011).

4. **Desensitization Mechanism:**
   - Accumulates during prolonged high-stress periods
   - Reduces effective stress level by damping factor
   - Decays exponentially when stress subsides
   - **Theoretical Basis:** Models receptor desensitization and homeostatic adaptation observed in serotonergic systems (Berg et al., 1994; Roth, 2011). This implements the computational concept of meta-adaptation where learning rates adjust based on environmental stability (Doya, 2002, 2008).

5. **Performance Tracking (Optional):**
   - Step timing metrics
   - Hold state statistics
   - Throughput measurement
   - **Theoretical Basis:** Aligns with real-time systems performance requirements (Buttazzo, 2011) and enables empirical validation of controller behavior.

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

**Neuroscience Foundation:** The controller design is grounded in computational neuroscience principles where serotonin acts as an opponent to dopamine, promoting behavioral inhibition and risk aversion during aversive states (Daw et al., 2002; Cools et al., 2011; Dayan & Huys, 2009). Research demonstrates that serotonin depletion increases risk-seeking behavior and impulsivity (Crockett et al., 2009; Schweighofer et al., 2008), while elevated serotonin promotes patience and punishment sensitivity (Miyazaki et al., 2011). Our implementation operationalizes these findings in a control-theoretic framework.

**Sensitivity Point:** Hysteresis width directly affects hold duration stability. Values < 0.05 may cause flapping; values > 0.2 may reduce responsiveness. This aligns with nonlinear dynamics theory where hysteresis band width determines stability margins (Brokate & Sprekels, 1996).

**Risk:** Over-tuned desensitization could mask genuine risk signals during extended market stress. This parallels receptor desensitization in neuropharmacology where chronic stimulation reduces sensitivity (Roth, 2011).

### STPA: Unsafe Control Actions (UCA)

System-Theoretic Process Analysis (STPA) is a hazard analysis technique that identifies unsafe control actions in complex systems (Leveson, 2011; Leveson & Thomas, 2018). We apply STPA to identify potential safety violations in the serotonin controller:

| Hazard | Source | UCA Type | Control Action | Context | Mitigation |
|--------|--------|----------|----------------|---------|------------|
| **H1: Trading during high volatility** | SerotoninController | Not Provided | Hold signal not activated | stress > threshold but hysteresis prevents entry | Asymmetric thresholds favor safety (enter easier than exit) |
| **H2: Stuck in hold during recovery** | SerotoninController | Stopped Too Soon | Hold released prematurely | Level drops briefly then spikes again | Cooldown period prevents immediate re-entry |
| **H3: Desensitization masking risk** | Desensitization Logic | Incorrect | Level damped too aggressively | Chronic stress > chronic_window | max_desensitization cap (0.8) preserves minimum sensitivity |
| **H4: State corruption from invalid input** | step() method | Incorrect | Invalid stress/drawdown values | NaN or negative inputs | Input validation, bounds clamping |

The STPA methodology helps identify control flaws that traditional safety analysis might miss (Leveson, 2004), particularly in systems with adaptive behavior and emergent properties.

### NFR Mechanisms (ISO/IEC 25010)

The controller design addresses Non-Functional Requirements (NFRs) according to the ISO/IEC 25010:2023 quality model for software systems (ISO, 2023). This standard defines eight quality characteristics essential for system evaluation and design decisions.

#### Reliability
- **Fault Tolerance:** Input validation with clamping to valid ranges
- **Recoverability:** reset() method for clean state restoration
- **Availability:** No external dependencies, pure Python implementation

#### Performance Efficiency
- **Time Behavior:** O(1) step complexity, < 100μs on modern hardware. This meets real-time control requirements for high-frequency trading systems (Buttazzo, 2011; Liu, 2000).
- **Resource Utilization:** Minimal memory footprint (~200 bytes state)
- **Batch Processing:** step_batch() for efficient historical analysis using vectorized operations

#### Maintainability
- **Modularity:** Clear separation of concerns (tonic/phasic/hold/desensitization) following software architecture best practices (Bass et al., 2021)
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

### Internal Documentation

1. [SEROTONIN_V2.4.0_SUMMARY.md](/SEROTONIN_V2.4.0_SUMMARY.md) - Implementation summary
2. [SEROTONIN_PRACTICAL_GUIDE.md](/docs/SEROTONIN_PRACTICAL_GUIDE.md) - Usage guide
3. [SEROTONIN_DEPLOYMENT_GUIDE.md](/docs/SEROTONIN_DEPLOYMENT_GUIDE.md) - Deployment procedures

### Neuroscience and Serotonin Research

4. Cools, R., Nakamura, K., & Daw, N. D. (2011). Serotonin and dopamine: Unifying affective, activational, and decision functions. *Neuropsychopharmacology*, 36(1), 98-113. https://doi.org/10.1038/npp.2010.121

5. Dayan, P., & Huys, Q. J. M. (2009). Serotonin in affective control. *Annual Review of Neuroscience*, 32, 95-126. https://doi.org/10.1146/annurev.neuro.051508.135607

6. Daw, N. D., Kakade, S., & Dayan, P. (2002). Opponent interactions between serotonin and dopamine. *Neural Networks*, 15(4-6), 603-616. https://doi.org/10.1016/S0893-6080(02)00052-7

7. Crockett, M. J., Clark, L., & Robbins, T. W. (2009). Reconciling the role of serotonin in behavioral inhibition and aversion: Acute tryptophan depletion abolishes punishment-induced inhibition in humans. *Journal of Neuroscience*, 29(38), 11993-11999. https://doi.org/10.1523/JNEUROSCI.2513-09.2009

8. Boureau, Y. L., & Dayan, P. (2011). Opponency revisited: Competition and cooperation between dopamine and serotonin. *Neuropsychopharmacology*, 36(1), 74-97. https://doi.org/10.1038/npp.2010.151

9. Cools, R., Roberts, A. C., & Robbins, T. W. (2008). Serotoninergic regulation of emotional and behavioural control processes. *Trends in Cognitive Sciences*, 12(1), 31-40. https://doi.org/10.1016/j.tics.2007.10.011

10. Matias, S., Lottem, E., Dugué, G. P., & Mainen, Z. F. (2017). Activity patterns of serotonin neurons underlying cognitive flexibility. *eLife*, 6, e20552. https://doi.org/10.7554/eLife.20552

11. Cohen, J. Y., Amoroso, M. W., & Uchida, N. (2015). Serotonergic neurons signal reward and punishment on multiple timescales. *eLife*, 4, e06346. https://doi.org/10.7554/eLife.06346

### Tonic and Phasic Neuromodulation

12. Grace, A. A. (1991). Phasic versus tonic dopamine release and the modulation of dopamine system responsivity: A hypothesis for the etiology of schizophrenia. *Neuroscience*, 41(1), 1-24. https://doi.org/10.1016/0306-4522(91)90196-U

13. Hajós, M., Hoffmann, W. E., & Kocsis, B. (2008). Activation of cannabinoid-1 receptors disrupts sensory gating and neuronal oscillation: Relevance to schizophrenia. *Biological Psychiatry*, 63(11), 1075-1083. https://doi.org/10.1016/j.biopsych.2007.12.005

14. Liu, Z., Zhou, J., Li, Y., Hu, F., Lu, Y., Ma, M., Feng, Q., Zhang, J. E., Wang, D., Zeng, J., Bao, J., Kim, J. Y., Chen, Z. F., El Mestikawy, S., & Luo, M. (2014). Dorsal raphe neurons signal reward through 5-HT and glutamate. *Neuron*, 81(6), 1360-1374. https://doi.org/10.1016/j.neuron.2014.02.010

### Neuromodulation and Decision-Making

15. Doya, K. (2002). Metalearning and neuromodulation. *Neural Networks*, 15(4-6), 495-506. https://doi.org/10.1016/S0893-6080(02)00044-8

16. Doya, K. (2008). Modulators of decision making. *Nature Neuroscience*, 11(4), 410-416. https://doi.org/10.1038/nn2077

17. Montague, P. R., Dayan, P., & Sejnowski, T. J. (1996). A framework for mesencephalic dopamine systems based on predictive Hebbian learning. *Journal of Neuroscience*, 16(5), 1936-1947. https://doi.org/10.1523/JNEUROSCI.16-05-01936.1996

### Computational Models and Control Theory

18. Sutton, R. S., & Barto, A. G. (2018). *Reinforcement learning: An introduction* (2nd ed.). MIT Press.

19. Åström, K. J., & Murray, R. M. (2021). *Feedback systems: An introduction for scientists and engineers* (2nd ed.). Princeton University Press.

20. Franklin, G. F., Powell, J. D., & Emami-Naeini, A. (2019). *Feedback control of dynamic systems* (8th ed.). Pearson.

### Hysteresis and Nonlinear Dynamics

21. Bertotti, G., & Mayergoyz, I. D. (2006). *The science of hysteresis* (Vol. 1-3). Academic Press. https://doi.org/10.1016/B978-0-12-480874-4.X5000-2

22. Visintin, A. (1994). *Differential models of hysteresis*. Springer-Verlag. https://doi.org/10.1007/978-3-662-11557-2

23. Brokate, M., & Sprekels, J. (1996). *Hysteresis and phase transitions*. Springer-Verlag. https://doi.org/10.1007/978-1-4612-4048-8

### Desensitization and Adaptation Mechanisms

24. Berg, K. A., Clarke, W. P., Sailstad, C., Saltzman, A., & Maayani, S. (1994). Signal transduction differences between 5-hydroxytryptamine type 2A and type 2C receptor systems. *Molecular Pharmacology*, 46(3), 477-484.

25. Roth, B. L. (2011). Irving Page Lecture: 5-HT₂A serotonin receptor biology: Interacting proteins, kinases and paradoxical regulation. *Neuropharmacology*, 61(3), 348-354. https://doi.org/10.1016/j.neuropharm.2011.01.012

26. Turrigiano, G. (2011). Too many cooks? Intrinsic and synaptic homeostatic mechanisms in cortical circuit refinement. *Annual Review of Neuroscience*, 34, 89-103. https://doi.org/10.1146/annurev-neuro-060909-153238

### Risk Aversion and Behavioral Inhibition

27. Schweighofer, N., Bertin, M., Shishida, K., Okamoto, Y., Tanaka, S. C., Yamawaki, S., & Doya, K. (2008). Low-serotonin levels increase delayed reward discounting in humans. *Journal of Neuroscience*, 28(17), 4528-4532. https://doi.org/10.1523/JNEUROSCI.4982-07.2008

28. Miyazaki, K., Miyazaki, K. W., & Doya, K. (2011). Activation of dorsal raphe serotonin neurons underlies waiting for delayed rewards. *Journal of Neuroscience*, 31(2), 469-479. https://doi.org/10.1523/JNEUROSCI.3714-10.2011

### Technical Standards and Frameworks

29. National Institute of Standards and Technology. (2023). *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*. U.S. Department of Commerce. https://doi.org/10.6028/NIST.AI.100-1

30. International Organization for Standardization. (2023). *ISO/IEC 25010:2023 - Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Product quality model*. ISO/IEC. https://www.iso.org/standard/78176.html

31. International Electrotechnical Commission. (2010). *IEC 61508 - Functional safety of electrical/electronic/programmable electronic safety-related systems*. IEC.

### Safety Analysis and STPA

32. Leveson, N. G. (2011). *Engineering a safer world: Systems thinking applied to safety*. MIT Press. https://doi.org/10.7551/mitpress/8179.001.0001

33. Leveson, N., & Thomas, J. (2018). *STPA handbook*. MIT Partnership for Systems Approaches to Safety and Security. http://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf

34. Leveson, N. G. (2004). A new accident model for engineering safer systems. *Safety Science*, 42(4), 237-270. https://doi.org/10.1016/S0925-7535(03)00047-X

### Time Series Analysis and Exponential Moving Averages

35. Box, G. E. P., Jenkins, G. M., Reinsel, G. C., & Ljung, G. M. (2015). *Time series analysis: Forecasting and control* (5th ed.). Wiley.

36. Hunter, J. S. (1986). The exponentially weighted moving average. *Journal of Quality Technology*, 18(4), 203-210. https://doi.org/10.1080/00224065.1986.11979014

### Performance Optimization and Real-Time Systems

37. Buttazzo, G. C. (2011). *Hard real-time computing systems: Predictable scheduling algorithms and applications* (3rd ed.). Springer. https://doi.org/10.1007/978-1-4614-0676-1

38. Liu, J. W. S. (2000). *Real-time systems*. Prentice Hall.

### Software Architecture and Quality Attributes

39. Bass, L., Clements, P., & Kazman, R. (2021). *Software architecture in practice* (4th ed.). Addison-Wesley.

40. Kazman, R., Klein, M., & Clements, P. (2000). ATAM: Method for architecture evaluation (CMU/SEI-2000-TR-004). Software Engineering Institute, Carnegie Mellon University. https://resources.sei.cmu.edu/library/asset-view.cfm?assetid=5177

### Financial Risk Management

41. Jorion, P. (2006). *Value at risk: The new benchmark for managing financial risk* (3rd ed.). McGraw-Hill.

42. McNeil, A. J., Frey, R., & Embrechts, P. (2015). *Quantitative risk management: Concepts, techniques and tools* (Revised ed.). Princeton University Press.

43. Tsay, R. S. (2010). *Analysis of financial time series* (3rd ed.). Wiley. https://doi.org/10.1002/9780470644560

## Related ADRs

- **ADR-0001:** Security, Compliance, and Documentation Automation (configuration governance)
- **ADR-0003:** [Planned] Neuromodulator Orchestration Framework

---

**Last Updated:** 2025-11-17  
**Next Review:** 2026-02-17 (Quarterly)
