# Serotonin ODE — Physics Contract

> Ground truth for all serotonin-related code in GeoSync.
> Read BEFORE modifying core/neuro/serotonin/, src/geosync/core/neuro/serotonin/,
> or any test in tests/core/neuro/serotonin/.

## 1. The Model

GeoSync's serotonin controller is an aversive-patience signal inspired by
Miyazaki et al. (2014) — serotonin neurons in dorsal raphe encode the
expectation of future reward during waiting, suppressing impulsive action.

### Aversive State Estimation

    A(t) = α·√(vol) + β·FE + γ·(L + 0.5·L²) + δ_ρ·(1 - ρ)

where:
- vol = market volatility (Weber-Fechner: √ for diminishing returns)
- FE = free energy (uncertainty, linear)
- L = cumulative losses (quadratic: pain intensifies)
- ρ = portfolio correlation losses

Saturated via tanh:  A_sat = 3·tanh(A/3) ∈ [0, 3)

### Sigmoid Gate (Phasic)

    gate = σ((A - θ_phase) / κ)    where σ(x) = 1/(1+e^{-x})

Tonic integration (leaky integrator):

    tonic(t+1) = (1 - d_eff)·tonic(t) + d_eff·(A + 0.5·phasic_burst)

where d_eff = decay_rate · (1 - 0.3·gate)

### Final Signal

    s(t) = σ(k·(tonic - θ)) · sensitivity

    sensitivity ∈ [0.1, 1.0]  (desensitization with exponential recovery)

### Two models — which invariant lives where

There are **two** serotonin models in the tree, and the invariants below apply to
them differently. Do not conflate them:

1. **Production controller** (the sigmoid/tonic system above; `serotonin_controller.py`)
   — the live decision path. INV-5HT1 (bounded output `s ∈ [0,1]`) holds here *by
   construction*: `σ ∈ (0,1)` times `sensitivity ∈ [0.1,1]`. It is not a dynamical
   Lyapunov system, so INV-5HT1 is a range guarantee, not a stability theorem.
2. **Reference ODE** (`core/neuro/serotonin_ode.py`) — a two-state RK4 flow used for
   verification/witnesses, *not* the live path. It is the model that can bear a
   **stability** claim: `lyapunov_parameter_certificate()` proves, from the
   parameters, that `V = ½(level−target)² + λ·desens²` is a strict Lyapunov function
   for the unforced sub-threshold flow (`α+γ>0` and `(α+γ)·2λμ > (δ/2)²`, `target=baseline`).
   `verify_lyapunov(trajectory)` is only an *empirical* descent witness on an
   already-clamped run — a positive/negative control, never the certificate itself.

So a Lyapunov/stability reading of "INV-5HT1" belongs to the reference ODE; the
production controller satisfies the bounded-output reading. Any code that needs a
proven stability guarantee must use the ODE's parameter certificate.

## 2. Physics Invariants

### INV-5HT1: Bounded output
    s(t) ∈ [0, 1] for all t
    Type: UNIVERSAL
    Proof: sigmoid σ ∈ (0,1), sensitivity ∈ [0.1,1.0], product ∈ [0,1)
    Falsification: s(t) < 0 or s(t) > 1 for ANY input combination

### INV-5HT2: Aversive state non-negative
    A(t) ≥ 0 for all t (all inputs are non-negative, tanh preserves sign)
    Type: UNIVERSAL
    Falsification: A(t) < 0

### INV-5HT3: Monotone stress response (qualitative)
    Increasing stress/vol/losses → non-decreasing serotonin signal
    (holding other inputs constant, single step, before desensitization)
    Type: QUALITATIVE
    Test: sweep one input while holding others, check non-decreasing s(t)
    Caveat: desensitization CAN cause s to decrease over time even with
    increasing stress — this is correct biology (receptor downregulation)

### INV-5HT4: Desensitization bounds
    sensitivity ∈ [0.1, 1.0] always
    Type: UNIVERSAL
    Proof: explicit clamp in code: max(0.1, ...) and min(1.0, ...)
    Falsification: sensitivity outside [0.1, 1.0]

### INV-5HT5: Temperature floor bounds
    temperature_floor ∈ [floor_min, floor_max] always
    Type: UNIVERSAL (derived from config)
    Proof: cubic interpolation between floor_min and floor_max

### INV-5HT6: Tonic integrator stability
    tonic_level remains finite and non-negative under bounded inputs
    Type: STABILITY
    Proof: leaky integrator with decay ∈ (0,1) and bounded input → bounded output
    Falsification: tonic_level → ∞ or NaN under finite inputs

### INV-5HT7: Hold/veto logic
    stress ≥ 1.0 OR |drawdown| ≥ 0.5 → veto = True (hard safety gate)
    Type: CONDITIONAL (safety-critical)
    Falsification: veto = False when stress ≥ 1.0

## 3. What Tests MUST Check

### Falsification (P0):
- s(t) ∈ [0,1] for random inputs (property test, hypothesis)
- sensitivity ∈ [0.1, 1.0] after arbitrary step sequences
- Hard veto fires at stress ≥ 1.0 and |drawdown| ≥ 0.5
- All outputs finite (no NaN/Inf) for finite inputs

### Convergence (P1):
- After sustained high stress, sensitivity → 0.1 (max desensitization)
- After stress removal, sensitivity recovers toward 1.0
- Tonic integrator decays toward 0 when aversive input = 0

### Monotonicity (P1):
- Single-step: higher vol → higher or equal serotonin (before desensitization)
- Single-step: higher losses → higher or equal serotonin
- Sweep: gate monotonically increases with aversive state

### Anti-patterns to avoid:
- Testing exact serotonin values (depends on full config, not physics)
- Ignoring desensitization when testing multi-step trajectories
- Asserting linear relationship (the model is sigmoid + sqrt + tanh, highly nonlinear)

## 4. Mapping to Market Behavior

| Neuroscience | GeoSync | Expected behavior |
|---|---|---|
| High serotonin | Risk aversion | Reduce position, hold |
| Low serotonin | Risk tolerance | Allow trading |
| Desensitization | Prolonged stress adaptation | Gradually resume trading even in bad conditions |
| Phasic burst | Sudden shock | Immediate veto |
| Tonic level | Background anxiety | Gradual position reduction |

## 5. Common Bugs This Theory Prevents

1. **Testing s == exact_value**: The signal depends on 6+ config params and
   nonlinear transforms. Test bounds and monotonicity, not exact values.

2. **Forgetting desensitization**: After 100 high-stress steps, sensitivity
   may be 0.1, so s(t) is ~10% of what a single-step test predicts.

3. **Confusing hold and veto**: hold = veto OR force_veto. veto comes from
   check_cooldown(). Both can be True independently.

4. **Wrong sign on drawdown**: drawdown is NEGATIVE (e.g., -0.05 for 5% loss).
   The controller coerces to negative, but tests should use correct convention.

5. **Ignoring thread safety**: SerotoninController uses RLock. Multi-threaded
   tests must account for lock contention and state ordering.
