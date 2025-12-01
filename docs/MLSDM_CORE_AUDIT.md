# MLSDM Core Audit Report

**Principal ML Engineer Assessment**  
**Date**: 2025-12-01  
**Scope**: Cognition, Memory, Rhythms, Telemetry subsystems  

---

## Executive Summary

This audit identifies "unstable" areas (experimental, weakly validated, or requiring strengthening) across the mlsdm core subsystems. The analysis covers:

1. **Cognition** — EMH state-space model, EKF estimation, policy controllers
2. **Memory** — Strategy memory, cortex memory repository, experimental GPU backends
3. **Rhythms** — Phase detection, Kuramoto synchronization, serotonin controller
4. **Telemetry** — Metrics emitters, decision exporters, monitoring

Each identified area includes a risk level (Critical/High/Medium/Low) and effort estimate (S/M/L/XL).

---

## 1. COGNITION Subsystem

### 1.1 EMH State-Space Model (`tradepulse/neural_controller/core/emh_model.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Hard-coded threat thresholds** | `_threat_mode()` uses fixed thresholds (dd>0.7=RED, dd>0.4=AMBER) without configurability | Medium | S |
| **Belief term gain fixed** | `belief_term_gain = 0.05` is hardcoded, should be configurable | Low | S |
| **No state persistence** | EMHState is transient; system loses state on restart | High | M |
| **Missing validation bounds** | Input observations (dd, liq, reg, vol) not validated before processing | Medium | S |

**Subtasks for Strengthening:**
1. **EMH-C1**: Externalize threat mode thresholds to config (Risk: Medium, Effort: S)
2. **EMH-C2**: Add state serialization/deserialization for EMHState (Risk: High, Effort: M)
3. **EMH-C3**: Input validation layer with bounds checking (Risk: Medium, Effort: S)
4. **EMH-C4**: Configurable belief_term_gain parameter (Risk: Low, Effort: S)

---

### 1.2 Extended Kalman Filter (`tradepulse/neural_controller/estimation/ekf.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Fixed process/measurement noise** | Q and R matrices use constant values from EKFConfig | Medium | M |
| **Jacobian approximation** | Using identity matrix F instead of proper linearization | High | L |
| **No divergence detection** | EKF can diverge without warning in extreme conditions | High | M |
| **Pinv numerical instability** | `np.linalg.pinv(S_cov)` can be unstable for ill-conditioned matrices | Medium | S |

**Subtasks for Strengthening:**
1. **EKF-C1**: Implement adaptive noise estimation based on innovation sequence (Risk: High, Effort: L)
2. **EKF-C2**: Add proper Jacobian computation for state transition (Risk: High, Effort: L)
3. **EKF-C3**: Implement divergence monitoring with covariance bounds checking (Risk: High, Effort: M)
4. **EKF-C4**: Replace pinv with regularized pseudo-inverse (Risk: Medium, Effort: S)

---

### 1.3 Basal Ganglia Controller (`tradepulse/neural_controller/policy/controller.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Q-values hardcoded** | Action value computation uses fixed coefficients (0.2, 0.3, 0.8, etc.) | Medium | M |
| **No exploration mechanism** | Pure exploitation via argmax without epsilon-greedy or UCB | Medium | S |
| **Temperature floor risk** | Very small temp values (near 1e-6) can cause numerical overflow | Low | S |

**Subtasks for Strengthening:**
1. **BG-C1**: Make Q-value coefficients configurable via PolicyConfig (Risk: Medium, Effort: M)
2. **BG-C2**: Add optional exploration mechanism (epsilon-greedy or softmax sampling) (Risk: Medium, Effort: S)
3. **BG-C3**: Add temperature bounds validation (Risk: Low, Effort: S)

---

## 2. MEMORY Subsystem

### 2.1 Strategy Memory (`core/agent/memory.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **In-memory only** | All strategy records kept in RAM with no persistence | High | M |
| **Unbounded growth** | max_records=256 but cleanup() requires manual invocation | Medium | S |
| **Time-based decay fragility** | Decay uses wall-clock time; paused systems lose historical context | Medium | M |
| **Tuple-based signature key** | `key()` method returns floats with precision=4, may collide | Low | S |

**Subtasks for Strengthening:**
1. **MEM-S1**: Add JSON/SQLite persistence layer for StrategyMemory (Risk: High, Effort: M)
2. **MEM-S2**: Implement automatic cleanup with configurable trigger (Risk: Medium, Effort: S)
3. **MEM-S3**: Use logical time (step count) instead of wall-clock for decay (Risk: Medium, Effort: M)
4. **MEM-S4**: Improve signature key with hash-based collision resistance (Risk: Low, Effort: S)

---

### 2.2 Cortex Memory Repository (`cortex_service/app/memory/repository.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **PostgreSQL-specific upsert** | Falls back to inefficient query-based upsert for non-PostgreSQL | Medium | M |
| **No transaction management** | Session operations lack explicit commit/rollback | High | S |
| **Missing index hints** | Large exposure tables may have slow lookups | Low | M |

**Subtasks for Strengthening:**
1. **MEM-R1**: Abstract dialect-specific operations into strategy pattern (Risk: Medium, Effort: M)
2. **MEM-R2**: Add explicit transaction boundaries with context managers (Risk: High, Effort: S)
3. **MEM-R3**: Document/add database index recommendations (Risk: Low, Effort: M)

---

### 2.3 Experimental FractalPELMGPU (`cortex_service/app/memory/experimental/fractal_pelm_gpu.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **EXPERIMENTAL module** | Explicitly marked as research-grade, not for production | Critical | XL |
| **No test coverage in CI** | Tests exist but may not run in standard pipelines (torch optional) | High | M |
| **Memory capacity enforced via list slicing** | O(n) eviction when exceeding capacity | Medium | M |
| **AMP deprecation** | `torch.cuda.amp.autocast()` deprecated in favor of new API | Low | S |

**Subtasks for Strengthening:**
1. **MEM-E1**: Create production-ready alternative or graduate with stability guarantees (Risk: Critical, Effort: XL)
2. **MEM-E2**: Add conditional CI test matrix for torch-enabled environments (Risk: High, Effort: M)
3. **MEM-E3**: Implement efficient circular buffer for capacity management (Risk: Medium, Effort: M)
4. **MEM-E4**: Migrate to `torch.amp.autocast()` API (Risk: Low, Effort: S)

---

## 3. RHYTHMS Subsystem

### 3.1 Phase Detector (`core/phase/detector.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Hardcoded thresholds** | PhaseThresholds defaults used without override mechanism | Medium | S |
| **Magic weight constants** | `composite_transition()` uses (0.4, 0.3, 0.3) weights without justification | Medium | S |
| **Missing phase transition history** | No tracking of phase changes over time | Low | M |

**Subtasks for Strengthening:**
1. **RHY-P1**: Accept PhaseThresholds injection in all public functions (Risk: Medium, Effort: S)
2. **RHY-P2**: Document/parameterize composite_transition weights (Risk: Medium, Effort: S)
3. **RHY-P3**: Add phase transition event logging/history (Risk: Low, Effort: M)

---

### 3.2 Adaptive Market Mind (`core/neuro/amm.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Homeostatic gain drift** | `_k` and `_theta` adapt continuously without bounds | High | S |
| **R_bar fixed at init** | Reference order parameter not updated dynamically | Medium | M |
| **Entropy estimator coupling** | Internal entropy (EWEntropy) tightly coupled; no external override | Low | S |

**Subtasks for Strengthening:**
1. **RHY-A1**: Add bounds on gain (_k) and threshold (_theta) adaptation (Risk: High, Effort: S)
2. **RHY-A2**: Implement running average for R_bar reference (Risk: Medium, Effort: M)
3. **RHY-A3**: Allow injection of external entropy estimator (Risk: Low, Effort: S)

---

### 3.3 Serotonin Controller (`core/neuro/serotonin/serotonin_controller.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **File-based locking** | Uses fcntl which is Unix-only; Windows incompatible | Medium | M |
| **Config mutation in meta_adapt** | Modifies config dict in-place, breaking immutability assumptions | High | S |
| **No rollback on config write failure** | If atomic replace fails, system in inconsistent state | Medium | S |
| **TACL guard injection optional** | Production systems may run without guardrails | Medium | S |

**Subtasks for Strengthening:**
1. **RHY-S1**: Abstract file locking to support cross-platform operation (Risk: Medium, Effort: M)
2. **RHY-S2**: Use copy-on-write pattern for config mutations (Risk: High, Effort: S)
3. **RHY-S3**: Implement full transactional config update with rollback (Risk: Medium, Effort: S)
4. **RHY-S4**: Require TACL guard in production mode (Risk: Medium, Effort: S)

---

### 3.4 Fractal Utilities (`core/neuro/fractal.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Small sample fallback** | Returns 0.5 (random walk) for < 50 samples without warning | Low | S |
| **Fixed window range** | hurst_exponent uses hardcoded 5 log-spaced windows | Medium | S |
| **No confidence intervals** | Point estimates without uncertainty quantification | Medium | M |

**Subtasks for Strengthening:**
1. **RHY-F1**: Add logging when falling back to default Hurst (Risk: Low, Effort: S)
2. **RHY-F2**: Make window selection configurable (Risk: Medium, Effort: S)
3. **RHY-F3**: Return confidence intervals for Hurst estimates (Risk: Medium, Effort: M)

---

## 4. TELEMETRY Subsystem

### 4.1 Metrics Emitter (`tradepulse/neural_controller/telemetry/metrics.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **In-memory buffer only** | No persistence or external sink configuration | High | M |
| **No buffer overflow protection** | Unbounded list growth if drain() not called | Medium | S |
| **Synchronous logging** | `log.info()` in emit() can block under load | Low | S |

**Subtasks for Strengthening:**
1. **TEL-M1**: Add configurable sink (file, Prometheus, OpenTelemetry) (Risk: High, Effort: M)
2. **TEL-M2**: Implement ring buffer with configurable size limit (Risk: Medium, Effort: S)
3. **TEL-M3**: Add async logging option for high-throughput scenarios (Risk: Low, Effort: S)

---

### 4.2 Decision Metrics Exporter

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Tail window fixed at 256** | May be too small for low-frequency trading | Low | S |
| **ES calculation assumes IID** | Expected Shortfall computed on raw rewards without windowing adjustment | Medium | M |
| **No export format** | Metrics returned as dict, no standardized schema | Low | M |

**Subtasks for Strengthening:**
1. **TEL-D1**: Make tail_window configurable via constructor (Risk: Low, Effort: S)
2. **TEL-D2**: Add windowed volatility adjustment for ES estimation (Risk: Medium, Effort: M)
3. **TEL-D3**: Define Pydantic schema for exported metrics (Risk: Low, Effort: M)

---

## 5. CROSS-CUTTING CONCERNS

### 5.1 Advanced Neuroeconomic Integration (`core/neuro/advanced/integrated.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Async-first API** | All methods are async but may block on CPU-intensive fractal analysis | High | M |
| **State persistence fragile** | load_state uses internal attribute access (e.g., `_expected`) | High | S |
| **No circuit breaker** | Cascading failures in DPA/AIC/NRE not isolated | Medium | M |

**Subtasks for Strengthening:**
1. **ADV-I1**: Offload fractal analysis to thread pool executor (Risk: High, Effort: M)
2. **ADV-I2**: Use proper serialization interface instead of attribute access (Risk: High, Effort: S)
3. **ADV-I3**: Implement circuit breaker pattern for component isolation (Risk: Medium, Effort: M)

---

### 5.2 Quantum-Inspired Utilities (`core/neuro/advanced/quantum.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Numerical stability** | Eigenvalue clipping at 1e-12 may mask numerical issues | Medium | S |
| **No validation of density matrix properties** | Inputs not checked for Hermitian/PSD | Medium | S |

**Subtasks for Strengthening:**
1. **ADV-Q1**: Add dynamic epsilon based on matrix condition number (Risk: Medium, Effort: S)
2. **ADV-Q2**: Validate density matrix properties with clear error messages (Risk: Medium, Effort: S)

---

### 5.3 Neuroplastic Reinforcement Engine (`core/neuro/advanced/nre.py`)

| Issue | Description | Risk | Effort |
|-------|-------------|------|--------|
| **Weight saturation** | Weights clamp to [0, 1] but decay can push to extremes | Medium | S |
| **Episode deque unbounded** | max_memory_size in config but not enforced on episodes | Low | S |
| **Context association keys fragile** | String-based regime_volatility keys prone to typos | Low | S |

**Subtasks for Strengthening:**
1. **ADV-N1**: Add soft saturation (sigmoid) instead of hard clamp (Risk: Medium, Effort: S)
2. **ADV-N2**: Enforce maxlen on _episodes deque (Risk: Low, Effort: S)
3. **ADV-N3**: Use enum or dataclass for context keys (Risk: Low, Effort: S)

---

## Priority Matrix

### Critical (Address Immediately)
| ID | Description | Effort |
|----|-------------|--------|
| MEM-E1 | Graduate or replace experimental FractalPELMGPU | XL |

### High Priority (Address in Next Sprint)
| ID | Description | Effort |
|----|-------------|--------|
| EMH-C2 | Add state persistence for EMHState | M |
| EKF-C1 | Adaptive noise estimation | L |
| EKF-C2 | Proper Jacobian computation | L |
| EKF-C3 | Divergence monitoring | M |
| MEM-S1 | Strategy memory persistence | M |
| MEM-R2 | Transaction management | S |
| MEM-E2 | CI test matrix for torch | M |
| RHY-A1 | AMM gain bounds | S |
| RHY-S2 | Config copy-on-write | S |
| TEL-M1 | Configurable telemetry sink | M |
| ADV-I1 | Async fractal offloading | M |
| ADV-I2 | Proper serialization | S |

### Medium Priority (Plan for Q1)
| ID | Description | Effort |
|----|-------------|--------|
| EMH-C1 | Threat threshold config | S |
| EMH-C3 | Input validation | S |
| EKF-C4 | Regularized pseudo-inverse | S |
| BG-C1 | Q-value coefficient config | M |
| BG-C2 | Exploration mechanism | S |
| MEM-S2 | Automatic memory cleanup | S |
| MEM-S3 | Logical time decay | M |
| MEM-R1 | Dialect abstraction | M |
| MEM-E3 | Circular buffer eviction | M |
| RHY-P1 | Phase threshold injection | S |
| RHY-P2 | Document composite weights | S |
| RHY-A2 | Dynamic R_bar | M |
| RHY-S1 | Cross-platform locking | M |
| RHY-S3 | Transactional config | S |
| RHY-S4 | Require TACL guard | S |
| RHY-F3 | Hurst confidence intervals | M |
| TEL-M2 | Ring buffer | S |
| TEL-D2 | Windowed ES | M |
| ADV-I3 | Circuit breaker | M |
| ADV-Q1 | Dynamic epsilon | S |
| ADV-Q2 | Density matrix validation | S |
| ADV-N1 | Soft weight saturation | S |

### Low Priority (Backlog)
| ID | Description | Effort |
|----|-------------|--------|
| EMH-C4 | Configurable belief_term_gain | S |
| BG-C3 | Temperature bounds | S |
| MEM-S4 | Hash-based signature keys | S |
| MEM-R3 | Index recommendations | M |
| MEM-E4 | Torch AMP migration | S |
| RHY-P3 | Phase history | M |
| RHY-A3 | External entropy injection | S |
| RHY-F1 | Fallback logging | S |
| RHY-F2 | Window configuration | S |
| TEL-M3 | Async logging | S |
| TEL-D1 | Tail window config | S |
| TEL-D3 | Pydantic schema | M |
| ADV-N2 | Episode deque maxlen | S |
| ADV-N3 | Context key enums | S |

---

## Effort Legend

| Code | Description | Person-Days |
|------|-------------|-------------|
| S | Small | 0.5-1 day |
| M | Medium | 2-3 days |
| L | Large | 5-8 days |
| XL | Extra Large | 10+ days |

---

## Recommendations

1. **Immediate Action**: Establish clear production-readiness criteria for experimental modules (MEM-E1)

2. **Sprint Priority**: Focus on state persistence (EMH-C2, MEM-S1) and EKF stability (EKF-C1, EKF-C3) to ensure system reliability

3. **Technical Debt Reduction**: Address configuration externalization items (EMH-C1, RHY-P1, BG-C1) as low-risk quick wins

4. **Testing Infrastructure**: Ensure experimental modules have dedicated CI coverage (MEM-E2)

5. **Observability**: Implement proper telemetry sinks (TEL-M1) before scaling operations

---

## Appendix: Component Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                        COGNITION                                 │
│  ┌─────────────┐   ┌──────────┐   ┌───────────────────────┐     │
│  │  EMH Model  │──▶│   EKF    │──▶│ Basal Ganglia Policy  │     │
│  └─────────────┘   └──────────┘   └───────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         MEMORY                                   │
│  ┌─────────────────┐   ┌─────────────────┐   ┌───────────────┐  │
│  │ Strategy Memory │   │ Cortex Repo     │   │ Experimental  │  │
│  │ (in-memory)     │   │ (PostgreSQL)    │   │ GPU Backend   │  │
│  └─────────────────┘   └─────────────────┘   └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         RHYTHMS                                  │
│  ┌──────────────┐   ┌──────────┐   ┌────────────────────────┐   │
│  │ Phase Detect │──▶│   AMM    │──▶│ Serotonin Controller   │   │
│  └──────────────┘   └──────────┘   └────────────────────────┘   │
│         │                                      │                 │
│         └───────────────┬──────────────────────┘                 │
│                         ▼                                        │
│              ┌─────────────────────┐                             │
│              │  Fractal Utilities  │                             │
│              └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        TELEMETRY                                 │
│  ┌───────────────────┐   ┌──────────────────────────────────┐   │
│  │ Metrics Emitter   │──▶│ Decision Metrics Exporter        │   │
│  └───────────────────┘   └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

*Document generated by Principal ML Engineer Audit Process*
