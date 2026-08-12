# Kuramoto Synchronization — Physics Contract

> This file is the GROUND TRUTH for all Kuramoto-related code in GeoSync.
> Read this BEFORE writing any test, implementation, or modification
> to modules in core/indicators/kuramoto*, core/physics/*kuramoto*,
> or any regime/synchronization logic.

## 1. The Model

N coupled phase oscillators:

    dθ_i/dt = ω_i + (K/N) · Σ_j sin(θ_j - θ_i)

where:
- θ_i ∈ [-π, π] = phase of oscillator i
- ω_i = natural frequency (drawn from distribution g(ω))
- K ≥ 0 = coupling strength (global parameter)
- N = number of oscillators

Order parameter (complex):

    Z(t) = R(t)·exp(iΨ(t)) = (1/N) · Σ_j exp(iθ_j(t))

    R(t) = |Z(t)| ∈ [0, 1]

R = 1: perfect sync. R = 0: complete desync. Ψ = mean phase.

## 2. Critical Coupling (MUST KNOW)

### Exact result (Kuramoto 1975, Strogatz 2000):

For symmetric, unimodal g(ω) with g(0) > 0:

    K_c = 2 / (π · g(0))

### Phase transition:

    K < K_c  →  R(t→∞) → 0     [INCOHERENT REGIME]
    K = K_c  →  R(t→∞) → 0⁺    [CRITICAL POINT]  
    K > K_c  →  R(t→∞) → R_∞ > 0  [PARTIALLY SYNCHRONIZED]

Near the transition (K slightly above K_c):

    R_∞ ∝ √(K - K_c)     [mean-field scaling, supercritical pitchfork]

### Why this matters for GeoSync:
When market oscillators (price bands) are weakly coupled (low correlation
regime), the order parameter R MUST decay. A test that checks R > 0 at
steady state with K ≪ K_c is WRONG — it tests the wrong physics.

## 3. Physics Invariants (HARD CONSTRAINTS)

### INV-K1: Order parameter bounds
    ∀t: 0 ≤ R(t) ≤ 1
    Type: UNIVERSAL. No exceptions. No approximations violate this.

### INV-K2: Subcritical decay
    K < K_c ⟹ R(t→∞) → 0
    Type: ASYMPTOTIC. For finite N, R fluctuates as O(1/√N).
    Test: after sufficient time, R < ε where ε = C/√N for some C.
    FALSIFICATION: if R stays above 0.5 with K = 0.1·K_c and N > 100, something is wrong.

### INV-K3: Supercritical order
    K > K_c ⟹ R(t→∞) = R_∞ > 0
    Type: ASYMPTOTIC. R_∞ depends on K and g(ω).
    Near transition: R_∞ ≈ √(16(K-K_c)/(π·K_c⁴·|g''(0)|))

### INV-K4: Monotonicity in K
    R_∞(K₁) ≤ R_∞(K₂) if K₁ < K₂  (for standard Kuramoto, no explosive sync)
    Type: CONDITIONAL — holds for standard model, NOT for explosive sync with
    frequency-degree correlation.

### INV-K5: Finite-size scaling
    For N oscillators, ⟨R⟩ ≈ O(1/√N) in incoherent regime.
    Variance of R: Var(R) ≈ O(1/N).
    Type: STATISTICAL. Test with ensemble averages over multiple realizations.

### INV-K6: Phase distribution
    K < K_c: phases uniformly distributed on [-π, π]
    K > K_c: phases cluster around Ψ (mean phase)
    Type: DISTRIBUTIONAL. Test with circular statistics (Rayleigh test).

### INV-K7: Energy dissipation (Lyapunov)
    The Kuramoto model has a Lyapunov function:
    V = -(K/2N) · Σ_{i,j} cos(θ_j - θ_i) = -(K·N/2)·R²
    dV/dt ≤ 0 (non-increasing along trajectories when no natural frequencies)
    With frequencies: potential landscape becomes more complex, but V still
    bounds the dynamics.

## 4. Higher-Order Kuramoto (Triadic)

    dθ_i/dt = ω_i + σ₁·Σ_j A_ij·sin(θ_j - θ_i) + σ₂·Σ_{j,k∈Δ(i)} sin(2θ_j - θ_k - θ_i)

Additional invariants:
- σ₂ > 0 can produce EXPLOSIVE synchronization (discontinuous transition)
- Hysteresis: forward K_c^↑ ≠ backward K_c^↓, and K_c^↓ < K_c^↑
- INV-K4 may FAIL (R can jump, not monotone in K)

## 5. Mapping to GeoSync Market Context

| Physics concept | GeoSync implementation | Module |
|---|---|---|
| θ_i (phase) | Hilbert transform of price band i | core/indicators/kuramoto.py |
| ω_i (natural freq) | Dominant frequency of band i | core/indicators/kuramoto.py |
| K (coupling) | Correlation strength / connectivity | core/config/kuramoto_ricci.py |
| R (order param) | Market coherence score | KuramotoFeature.compute() |
| K_c (critical) | Regime transition threshold | core/physics/explosive_sync.py |
| Hysteresis | Crisis persistence | ESCircuitBreaker |

## 6. What Tests MUST Check vs What They MUST NOT

### MUST (falsification-class):
- R stays in [0,1] for ALL inputs (INV-K1)
- R → 0 when K = 0 (trivially incoherent) (INV-K2 limit)
- R → 1 when all ω_i identical and K > 0 (trivially coherent)
- R increases with K for standard model (INV-K4)
- Finite-size scaling: R ~ 1/√N for incoherent state (INV-K5)

### MUST NOT:
- Assert R == 0.0 exactly (finite-size fluctuations always exist)
- Assert R > specific_value without knowing K/K_c ratio
- Use deterministic assertions on stochastic quantities without ensemble
- Test convergence time without accounting for N-dependence (τ ~ N for finite-size)
- Assume INV-K4 holds for higher-order / explosive sync models

## 7. Common Bugs This Theory Prevents

1. **Testing R > 0 at subcritical K**: The test passes by accident on small N
   (finite-size effect) but the physics is wrong.

2. **Hardcoding K_c**: K_c depends on g(ω). If you change the frequency
   distribution, K_c changes. Always compute K_c from the distribution.

3. **Confusing R with correlation**: R is phase synchrony, not Pearson
   correlation. Two perfectly anticorrelated oscillators have R ≈ 0, not R = -1.

4. **Ignoring transients**: R(t=0) depends on initial conditions. Physics
   predictions are about R(t→∞). Always simulate long enough.

5. **Wrong ε for convergence**: Checking R < 0.01 for N=10 is wrong.
   For N=10, R fluctuates as ~1/√10 ≈ 0.32 even in incoherent state.
   Use ε = C/√N with C ≈ 2-3 for 95% confidence.
