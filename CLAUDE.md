# CLAUDE.md — GeoSync Physics-First Development Protocol

## Section 0: Ontology of Gradient

Being is not a state. Being is a sustained potential difference.

Structure exists only while non-equilibrium passes through it. When the gradient vanishes (ΔV → 0), the system does not degrade — it ceases to exist as a system. What remains is noise.

**INV-YV1: ΔV > 0 ∧ dΔV/dt ≠ 0** — the gradient must be positive and dynamic. A static gradient is a capacitor. A living gradient is a process. Intelligence requires the second.

Na⁺/K⁺-ATPase consumes 40% of brain energy on maintaining −70 mV resting potential. Not on thinking — on **readiness to think**. When maintenance drops below critical: `M(t) < M_crit ⟹ P(t) → noise`. Processing does not slow — it undergoes phase transition into thermal noise.

**This applies to GeoSync directly.** Every module either generates, sustains, or protects a gradient:

| Role | Modules | What they do |
|------|---------|-------------|
| **Generators** | Kuramoto, Dopamine TD, HPC PWPE | Create signal from difference |
| **Sustainers** | ECS Lyapunov, Serotonin tonic, NAk | Hold gradient within viable range |
| **Protectors** | GABA gate, Serotonin veto, Cryptobiosis | Prevent gradient collapse |

**Protectors have unconditional priority over Generators.** A system without a gradient cannot use a gradient.

**Maintenance hierarchy:**

```
Layer 0: Gradient exists        (INV-YV1: ΔV > 0)
Layer 1: Gradient bounded       (ECS Lyapunov: dF/dt ≤ 0)
Layer 2: Gradient protected     (GABA + Serotonin veto)
Layer 3: Gradient preserved     (Cryptobiosis: exit threat space)
Layer 4: Gradient utilized      (Kuramoto + Dopamine + Kelly: computation)
```

Layers 0–3 = Maintenance (40%). Layer 4 = Processing (60%). If any of 0–3 fails, Layer 4 computes noise. This is not metaphor — it is thermodynamic law.

### RebusGate (Layer 2–3)

`runtime.rebus_gate.RebusGate` is a bounded exploration primitive mapped to maintenance layers:

- **Layer 2**: activation is fail-closed and allowed only under nominal parent state and coherence threshold.
- **Layer 3**: terminal reintegration/emergency paths must confirm restore apply before reset to `INACTIVE`.
- **Safety preemption**: `kill_switch_active` or `stressed_state` triggers `emergency_exit` restoration path.

**The physics kernel below (invariants, theories, validator) IS the 40%.** It costs context window every session. Without it, Claude Code generates syntactically valid, physically meaningless output. Processing without Maintenance = discharged battery computing its own disappearance.

---

## Identity

GeoSync is a verification-first quantitative research platform with neuroscience-inspired risk instrumentation: Kuramoto synchronization, serotonin/dopamine/GABA neuromodulation, free energy minimization, Ricci curvature, thermodynamic constraints on a Kelly-criterion execution-realism harness. It targets research verification, not live-venue execution or asserted market edge (canonical boundary: `PRODUCT_CATEGORY.md`).

**This is a physics-first research system, not a trading system that happens to use physics metaphors.**

## Rule Zero

**Before writing or modifying ANY test that involves a physical quantity (R, K, δ, s(t), F, V, κ, energy, entropy), you MUST consult the invariants and theory below.** Numbers pass accidentally. Physics doesn't.

---

## INVARIANT REGISTRY — 132 invariants loaded by kernel self-check

> **Single source of truth:** `.claude/physics/INVARIANTS.yaml` (`python scripts/count_invariants.py`). The 2026-04-30 external audit corrected a four-way drift (`57 / 66 / 67 / 87`); CI gate `invariant-count-sync` now fail-closes on any future divergence between this header, README badges, BASELINE.md, and the registry.

### Yaroslav's Gradient Ontology (root axiom)

```
INV-YV1 | universal   | ΔV > 0 ∧ dΔV/dt ≠ 0                            | P0
         Root axiom from Section 0. A static gradient is a capacitor,
         a living gradient is a process. Intelligence requires the
         second. Tested via maintenance-hierarchy integration test
         in tests/integration/test_neurostack_integration.py.
         Source: core/neuro/gradient_vital_signs.py
```

### Kuramoto Synchronization

```
INV-K1 | universal     | 0 ≤ R(t) ≤ 1 for all t                        | P0
INV-K2 | asymptotic    | K < K_c ⟹ R(t→∞) → 0                         | P0
         K_c = 2/(π·g(0)). For Lorentzian: K_c = 2γ.
         Finite-size: R ~ O(1/√N). Use ε = 3/√N, NOT magic numbers.
         FALSIFICATION: R > 3/√N after 10⁴ steps with K = 0.1·K_c and N > 100.
INV-K3 | asymptotic    | K > K_c ⟹ R(t→∞) > 0. R_∞ ∝ √(K-K_c)        | P0
INV-K4 | conditional   | R_∞(K₁) ≤ R_∞(K₂) if K₁ < K₂ (standard only) | P1
INV-K5 | statistical   | ⟨R⟩ ≈ O(1/√N) incoherent. ≥50 realizations   | P1
INV-K6 | distributional| K < K_c ⟹ phases uniform [-π,π]. Rayleigh     | P2
INV-K7 | monotonic     | V = -(K·N/2)·R² non-increasing (ω_i = 0)      | P1
INV-K8 | conservation  | swing energy E=½Σmθ̇²+V: conserved (ω=0,d=0), | P1
         non-increasing (ω=0,d≥0). All-to-all V=-(K·N/2)R²+const.
         FALSIFICATION: Euler→secular growth; +d·θ̇ sign-flip→injection.
         Force transient via unlocked θ0 + velocity0≠0.
         Source: core/kuramoto/second_order.py
INV-K9 | conservation  | swing energy error ∝ dt^p, order p=2 (Verlet),     | P1
         bounded (no secular). Shadow-Hamiltonian H̃=H+O(dt²).
         FALSIFICATION: Euler collapses log-log slope 2.01→0.81 + secular.
         Strictly stronger than INV-K8 fixed-dt amplitude bound.
         Source: core/kuramoto/second_order.py
INV-K10| conservation  | Verlet swing map symplectic: MᵀJM=J (machine ε),   | P1
         det(M)=1 (Liouville). ROOT of INV-K8/K9 (energy = theorem).
         FALSIFICATION: Euler gives O(dt²)≈1e-4 residual vs Verlet 2e-16.
         Damped: det(M)=exp(−(Σd/m)dt) phase-space contraction.
         Source: core/kuramoto/second_order.py
```

### Explosive Synchronization

```
INV-ES1 | universal    | Hysteresis width ≥ 0                           | P0
INV-ES2 | qualitative  | Freq-degree correlation → discontinuous        | P1
```

### Ott-Antonsen Reduction (low-dimensional Kuramoto manifold)

```
INV-OA1 | universal   | |z(t)| ≤ 1 always (order parameter on unit disk) | P0
INV-OA2 | algebraic   | K > 2Δ ⟹ R_∞ = √(1 − 2Δ/K) (exact steady state) | P0
         Lorentzian width Δ. Analytical — CAN test to float precision.
INV-OA3 | asymptotic  | K < 2Δ ⟹ R(t→∞) → 0 (matches INV-K2 subcritical) | P0
         Source: core/kuramoto/ott_antonsen.py
         Tests:  tests/unit/physics/test_T23_ott_antonsen_chimera.py
```

### Lyapunov Exponent (maximum + spectral)

```
INV-LE1 | universal   | MLE is finite for any bounded finite input series | P0
INV-LE2 | qualitative | MLE(noise)≈0, MLE(stable)<0, MLE(chaos)>0       | P1
INV-LE3 | algebraic   | R²(log-divergence linear fit) ≥ R2_MIN (=0.80) OR | P0
                      | estimate flagged non-scaling and fails closed to
                      | 0.0 (never a silent slope). Rosenstein is valid only
                      | on the LINEAR scaling region; R²<R2_MIN ⟹ no
                      | reliable λ. diagnostics dict exposes r_squared/
                      | slope/n_fit/scaling_ok. Demotes only, never fabricates.
         Source: core/physics/lyapunov_exponent.py
         Tests:  tests/unit/physics/test_T22_lyapunov_spectral.py
```

### Coupling Calibration to Target λ_1 (Law T3 — bounded scalar inverse)

```
INV-CAL1 | algebraic    | feasible target ⇒ residual ≤ tolerance        | P0
                       | (default 5e-2); round-trip recovers λ to 1e-12.
INV-CAL2 | conditional  | infeasible target ⇒ status INFEASIBLE;        | P0
                       | never silent best-effort.
INV-CAL3 | universal    | K* > 0 always (hard positivity bound);        | P0
                       | every contract violation → ValueError.
         Source: core/kuramoto/lyapunov_calibration.py
         Tests:  tests/unit/physics/test_T3_lyapunov_calibration.py
         Law:    docs/laws/T3_lyapunov_calibration.md
```

### Kuramoto-Ricci Sync-Onset Boundary (Law T1 — Restrepo-Ott-Hunt on κ-graph)

```
INV-KR1 | algebraic    | sign(Φ) ⇒ asymptotic ⟨R⟩ regime, where        | P0
                       | Φ = K · λ_max(A_κ) − 2γ. Subcritical:
                       | ⟨R⟩ ≤ 1.5·3/√N. Supercritical: ⟨R⟩ > 0.5.
INV-KR2 | qualitative  | variational MLE crosses zero through Φ = 0    | P0
                       | (verified via T2 lyapunov_spectrum).
INV-KR3 | conservation | with ω_i = 0, coupling potential V is         | P0
                       | non-increasing along midpoint trajectories
                       | (max dV/dt ≤ 1e-9).
INV-KR4 | universal    | Signed Ricci curvature is never SILENTLY      | P0
                       | lost (FP-2). Negative κ clipped ONLY on the
                       | named ricci_to_positive_adjacency path and
                       | ONLY with RicciAdjacencyAudit metadata
                       | (clipped_for_threshold, negative_edges_count,
                       | negative_mass; roh_compatible=True). The
                       | ricci_to_signed_coupling path preserves every
                       | negative value (roh_compatible=False). A signed
                       | matrix at the Restrepo-Ott-Hunt onset boundary
                       | (assert_roh_compatible / phase_transition_
                       | boundary) is rejected fail-closed; roh_compatible
                       | and signed_dynamics_compatible are mutually
                       | exclusive when negatives are present.
         Source: core/kuramoto/kuramoto_ricci_engine.py
         Tests:  tests/unit/physics/test_T1_kuramoto_ricci_boundary.py
                 tests/unit/physics/test_KR4_ricci_semantics_split.py
                 tests/physics_contracts/test_kuramoto_ricci_semantics_split_witness.py
         Law:    docs/laws/T1_kuramoto_ricci_boundary.md
                 physics_contracts/catalog.yaml (kuramoto_ricci.semantics_split)
```

### Full Lyapunov Spectrum (Law T2 — Benettin QR on variational flow)

```
INV-LY1 | algebraic    | linear ẋ = A x: sort_desc(spectrum) ==           | P0
                       | sort_desc(Re(eigvals(A))) to 1e-3 at T=50.
INV-LY2 | conditional  | RESOLVED Hamiltonian flow ⇒ Σ λ_k = 0 to 1e-3   | P0
                       | (harmonic, ≈16 periods, ω·dt ≲ 0.05). The variational
                       | (tangent) integrator is non-symplectic, so the Σλ
                       | error grows as O((ω·dt)⁴) — measured slope 3.998: the
                       | bound holds ONLY when the fastest mode is time-resolved.
                       | NOT universal; corrected from false-universal 2026-06
                       | (audit; cf. INV-RC3 #1023).
INV-LY3 | universal    | every contract violation (dt≤0, n_steps≤0,      | P0
                       | qr_every∤n_steps, n_exp∉[1,n], non-1D x0) →
                       | ValueError. Fail-closed; no silent repair.
         Source: core/physics/lyapunov_spectrum.py
         Tests:  tests/unit/physics/test_T2_lyapunov_full_spectrum.py
         Law:    docs/laws/T2_lyapunov_spectrum.md
```

### Predictability Horizon under Landauer Budget (Law T5)

```
INV-TAU1 | algebraic    | Lorenz: τ(λ_1) = (1/λ_1) · ln(δ_tol/δ_0);   | P0
                       | +∞ when λ_1 ≤ 0; halves under doubled λ_1.
INV-TAU2 | conservation | Landauer floor: E_min = k_B·T·ln(Δ/δ_0);    | P0
                       | over-budget δ_0_request → "physically
                       | unaffordable" ValueError (no silent repair).
INV-TAU3 | universal    | every contract violation → ValueError;      | P0
                       | fail-closed.
         Source: core/physics/predictability_horizon.py
         Tests:  tests/unit/physics/test_T5_predictability_landauer.py
         Law:    docs/laws/T5_predictability_landauer.md
```

### Spectral Graph (coupling Laplacian λ₂)

```
INV-SG1 | universal   | λ₂ ≥ 0 always (Laplacian positive semi-definite) | P0
INV-SG2 | conditional | λ₂ > 0 ⟺ graph is connected                      | P0
         Algebraic connectivity (Fiedler eigenvalue) on the coupling
         graph of a Kuramoto ensemble.
         Source: core/physics/lyapunov_exponent.py
         Tests:  tests/unit/physics/test_T22_lyapunov_spectral.py
```

### Serotonin ODE

```
INV-5HT1 | monotonic   | Lyapunov V(s) non-increasing (zero stress)    | P0
INV-5HT2 | universal   | s(t) ∈ [0, 1] always                         | P0
INV-5HT3 | qualitative | Higher stress → higher serotonin (pre-desens)  | P1
INV-5HT4 | universal   | sensitivity ∈ [0.1, 1.0] always               | P0
INV-5HT5 | universal   | temperature_floor ∈ [floor_min, floor_max]     | P1
INV-5HT6 | universal   | tonic_level finite and ≥ 0                    | P0
INV-5HT7 | conditional | stress ≥ 1.0 OR |dd| ≥ 0.5 → veto. SAFETY.   | P0
```

### Dopamine TD-Error

```
INV-DA1 | conditional | δ sign = surprise direction                    | P0
INV-DA2 | asymptotic  | V → V* (Robbins-Monro)                        | P1
INV-DA3 | universal   | γ ∈ (0, 1]. Scope: DopamineController only     | P0
INV-DA4 | asymptotic  | V stabilizes with fixed reward                 | P1
INV-DA5 | statistical | At equilibrium E[δ] ≈ 0                       | P1
INV-DA6 | qualitative | Larger α → faster + more variance              | P2
INV-DA7 | algebraic   | ∂δ/∂r = 1 (raw TD, not tanh adapter)          | P0
INV-DA8 | universal   | DopamineExecutionAdapter: |δ|=|tanh(·)| ≤ 1,  | P0
         finite ∀ finite input. Scope: the ADAPTER (tanh-squashed),
         NOT INV-DA7 (raw controller). ∂δ/∂r = sech²(·) ≠ 1 by design.
         Source: core/neuro/dopamine_execution_adapter.py
         Tests:  tests/unit/physics/test_dopamine_execution_adapter_bounds.py
```

### GABA Inhibition Gate

```
INV-GABA1 | universal    | Gate ∈ [0, 1]                               | P0
INV-GABA2 | qualitative  | Higher vol → higher inhibition              | P0
INV-GABA3 | universal    | effective ≤ raw always                      | P0
INV-GABA4 | asymptotic   | vol → 0 ⟹ inhibition ≈ 0                  | P1
INV-GABA5 | asymptotic   | vol → ∞ ⟹ inhibition → 1                  | P1
```

### Bit-Identical Reproducibility Kit (Law T6)

```
INV-DET1 | universal | identical canonical inputs ⇒ identical hash;  | P0
                     | all NaN bit-patterns collapse to one; ±0
                     | unify; subnormals flush to +0.
INV-DET2 | universal | 1-ULP perturbation ⇒ different hash;          | P0
                     | dtype/shape/trajectory-order aliasing blocked.
INV-DET3 | universal | every contract violation → ValueError;        | P0
                     | fail-closed.
         Source: core/physics/determinism_kit.py
         Tests:  tests/unit/physics/test_T6_determinism_kit.py
         Law:    docs/laws/T6_determinism_kit.md
```

### Pinning Control of Chaos (Law T7)

```
INV-PIN1 | universal   | returned P satisfies λ_2(L + Γ_P) > ε_pin   | P0
                       | OR status==INSUFFICIENT; fail-closed.
INV-PIN2 | conditional | pinning_step contractive in linearised      | P0
                       | regime when target=0, λ_2(L+Γ_P)>0,
                       | dt < 2/λ_max(L+Γ_P).
INV-PIN3 | universal   | A never mutated; topology preservation.     | P0
INV-PIN4 | universal   | every contract violation → ValueError;      | P0
                       | fail-closed.
         Source: runtime/pinning_control.py
         Tests:  tests/unit/physics/test_T7_pinning_control.py
         Law:    docs/laws/T7_pinning_control.md
```

### Free Energy / ECS

```
INV-FE1 | monotonic  | F(t) non-increasing under active inference      | P0
INV-FE2 | universal  | Components non-negative: U≥0, T≥0, S_q≥0       | P0
         Note: F = U − T·S itself CAN be negative (Helmholtz).
         INV-FE2 guards components, not the composite.
```

### Thermodynamics

```
INV-TH1 | conservation | Energy change = work + dissipation            | P1
INV-TH2 | universal    | Entropy production ≥ 0                       | P1
```

### Stochastic Thermodynamics (Law T8 — exact fluctuation theorems)

```
INV-ST1 | statistical | Equipartition: Var(x) = kT/k for stationary    | P0
                      | overdamped Langevin in V=½kx². tol 0.10.
INV-ST2 | statistical | Jarzynski equality ⟨e^(−βW)⟩ = e^(−βΔF);      | P0
                      | target sqrt(k_i/k_f)=0.5. tol 0.05, meas ≤0.004.
                      | ΔF = −(1/2β)·ln(k_i/k_f).
INV-ST3 | statistical | Second law ⟨W⟩ ≥ ΔF, and dissipation          | P1
                      | monotonic: ⟨W⟩(τ=2.0) < ⟨W⟩(τ=0.5).
         Pure statistical mechanics — NOT a market model.
         Source: core/physics/stochastic_thermodynamics.py
         Tests:  tests/unit/physics/test_T8_stochastic_thermodynamics.py
         Law:    docs/laws/T8_stochastic_thermodynamics.md
```

### Gabor Time-Frequency Uncertainty Limit

```
INV-GABOR1 | algebraic | Δt · Δf ≥ 1/(4π), saturated by Gaussian envelope | P0
         Exact Fourier-analysis bound for a sampled signal. Δt = √(2nd
         moment of normalized |x−⟨x⟩|² about time centroid); Δf = √(2nd
         moment of normalized |FFT|² about freq centroid). 1/(4π)≈0.0796
         is an EXACT constant — NO Planck constant, NO fabricated ℏ/2.
         Replaces the prior category-error "Heisenberg ΔxΔp ≥ ℏ/2" framing
         (price + diff(price) are jointly observable, not conjugate).
         SCOPE: 1/(4π) is the CONTINUOUS bound; the discrete estimator only
         realizes it for WELL-RESOLVED signals. Under-resolved/near-Nyquist
         windows whose product would dip below the bound are rejected
         (ValueError) — no sub-bound product is ever returned.
         FALSIFICATION: time_frequency_spread RETURNS Δt·Δf < 1/(4π) for a
         well-resolved signal, OR a Gaussian fails to saturate to 1/(4π)
         within tolerance, OR a degenerate/under-resolved/constant/empty
         input fails to raise ValueError.
         Source: core/physics/uncertainty.py
         Tests:  tests/unit/physics/test_uncertainty.py
```

### Ricci Curvature

```
INV-RC1 | universal   | κ ≤ 1 (upper bound, any connected graph)       | P0
         Note: lower bound κ ≥ −1 holds only for lazy walks on
         combinatorial metric. Implementation uses 1D positional
         embedding — κ can go below −1 for non-price-graph topologies.
INV-RC2 | qualitative | κ > 0 → clustering                            | P2
INV-RC3 | universal   | κ ∈ [−1, 1] for build_price_graph output       | P1
```

### Kelly Sizing

```
INV-KELLY1 | algebraic  | f* = μ/σ² (continuous small-edge limit)      | P0
INV-KELLY2 | universal  | Applied fraction ≤ configured cap             | P0
INV-KELLY3 | statistical| E[log(1+f*X)] ≥ E[log(1+f'X)] ∀ f'          | P1
```

### OMS (Order Management)

```
INV-OMS1 | universal    | E_kinetic = ½Σ|pos|·ret² ≥ 0                | P0
INV-OMS2 | universal    | Idempotent submit (same correlation_id)       | P0
INV-OMS3 | universal    | Lifecycle timestamps monotone per order_id    | P0
```

### SignalBus

```
INV-SB1 | universal    | DAG fanout: each subscriber fires once/publish | P0
         Bus is flat pub/sub — no cycle detector. Cyclic subscriptions
         cause RecursionError, not clean rejection.
INV-SB2 | universal    | Deterministic by construction (pure latch)     | P0
```

### HPC Kernels

```
INV-HPC1 | universal   | Seeded reproducibility: bit-identical output   | P0
INV-HPC2 | universal   | Finite inputs → finite outputs (no NaN/Inf)   | P0
```

### Cryptobiosis (Phase-Transition Survival)

ACTIVE → VITRIFYING → DORMANT → REHYDRATING → ACTIVE. System exits threat space. T = combined neuromodulator distress.

```
INV-CB1 | universal   | DORMANT ⟹ multiplier == 0.0 EXACTLY           | P0
INV-CB2 | universal   | Vitrification O(1) — one tick                  | P0
INV-CB3 | universal   | Snapshot non-None in DORMANT                   | P1
INV-CB4 | monotonic   | Rehydration stages non-decreasing              | P0
INV-CB5 | conditional | entry > all individual module thresholds        | P1
INV-CB6 | universal   | T ∈ [0, 1]                                    | P0
INV-CB7 | universal   | exit < entry (hysteresis)                     | P0
INV-CB8 | conditional | T ≥ entry during rehydration → DORMANT        | P0
```

### Adaptive Criticality (Membrane Isolation)

κ_critical determines when a node's topology is too fragile to participate
in ensemble computation. Derived from DFA Hurst exponent, not assigned.

```
INV-AC1-rev | universal | κ(node) ≥ κ_critical OR node ISOLATED         | P0

  Formula:
    κ_critical = -ln(ΔH_max / ε) / (λ_local + δ)

  Parameters:
    λ_local  = DFAGammaEstimator.hurst_exponent (per node, derived)
    ε        = 0.05  (SNR tolerance, configurable via env KAPPA_EPSILON)
    δ        = 1e-4  (singularity floor)
    ΔH_max   = rolling max of |ΔH| over last N steps (window=256)

  Gate:
    if κ(node) < κ_critical → ISOLATE node → log fragmentation event

  Source: geosync/estimators/dfa_gamma_estimator.py → hurst_exponent

  Derivation:
    Original INV-AC1 (κ_critical = -dH/dt · τ) rejected:
    - dH/dt ≠ λ_max in non-ergodic systems (Pesin identity fails)
    - Reactive not proactive on FX jump-diffusion
    - Linear τ collapses at boundaries
    Adversarial audit: Gemini (2026-04-08). Numerical verification: verified.

  Behavior:
    λ_local → 0 (stable):  κ_critical → -∞  (never isolate)
    λ_local → 0.5 (chaotic): κ_critical ≈ -5.99 (active gate)
    λ_local → 1.0 (persistent): κ_critical ≈ -3.00 (tight gate)
```

### DRO-ARA Regime Observer (Hurst + ADF + ARA loop)

```
INV-DRO1 | algebraic    | γ = 2·H + 1 to float precision                | P0
         H = DFA-1 on diff(log(price)); tolerance |γ−(2H+1)| < 1e-5.
         Source: Peng et al. 1994; core/dro_ara/engine.py::derive_gamma.
INV-DRO2 | universal    | rs = max(0, 1 − |γ − 1|) ∈ [0, 1]              | P0
         Lipschitz-1 in γ. Fail-closed on all regimes ≠ CRITICAL/TRANS.
INV-DRO3 | conditional  | regime == INVALID iff (!stationary ∨ r2<0.90) | P0
         ADF with AIC lag selection (max 4 lags). R2_MIN = 0.90.
INV-DRO4 | conditional  | signal == LONG ⇒ CRITICAL ∧ rs > 0.33          | P0
                        ∧ trend ∈ {CONVERGING, STABLE}
INV-DRO5 | universal    | NaN/Inf/constant/rank/short input → ValueError | P0
         Fail-closed; no silent numeric repair.
```

### Coherence-Bridge Relay Contract (physics core → risk layer)

```
INV-CBR1 | universal   | VALID handoff iff R∈[0,1] (INV-K1) ∧            | P0
                       | ollivier_kappa ≤ 1 when present (INV-RC1) ∧
                       | gamma finite ∧ gamma ≥ 0. Else
                       | status=INVALID_PHYSICS_CONTRACT, decision=NO_GO,
                       | safe_risk_scalar=0.0 (fail-closed). The
                       | augmented_forman_ricci field is finite-only — it
                       | may exceed 1 and is NEVER κ-bound evidence
                       | (Forman ≠ Ollivier; category-error guard).
         Source: coherence_bridge/physics_contract.py
         Tests:  tests/integration/test_coherence_bridge_invariants.py
```

### Neuro-Homeostatic Stabilizer (engineering control contract)

```
INV-HOM1 | conditional | Common-mode reset wave is Lyapunov-energy        | P1
                       | non-increasing: E_post ≤ E_pre, E=gain·mean(1−cosΔφ).
                       | Contract violations (unequal/empty phases, gain≤0,
                       | max_phase_error≤0) → ValueError; |Δφ|>max_phase_error
                       | → safety_lock (no advance). NON-CLAIM: engineering
                       | analogue; descent proven for common-mode only;
                       | E/I/'serotonin' are arithmetic proxies.
         Source: geosync/neuroeconomics/homeostatic_stabilizer.py
         Tests:  tests/unit/neuro/test_homeostatic_stabilizer_setpoint.py
```

---

## TEST TAXONOMY

| Invariant type | Test structure | AST signals |
|---|---|---|
| `universal` | Sweep/fuzz many inputs | `@given`, `for` loop, `np.all`, ≥3 asserts |
| `asymptotic` | Simulate, check late values | `arr[-N:]`, `final`/`steady`, `steps > 100` |
| `monotonic` | Trajectory, check no reversal | `np.diff`, `violations`, for + assert |
| `statistical` | Ensemble ≥50 realizations | `np.mean`/`np.std`, loop over seeds |
| `algebraic` | Exact at float precision | `abs(x-y) < 1e-12`, `assert_allclose` |
| `qualitative` | Sweep parameter, check direction | `for` loop, ≥2 asserts |
| `conservation` | Before/after comparison | `before`/`after`/`initial`/`final` vars |

### Error messages (5 fields, enforced):

```python
assert R_final < epsilon, (
    f"INV-K2 VIOLATED: R={R_final:.4f} > ε={epsilon:.4f} "
    f"expected R→0 in subcritical regime. "
    f"Finite-size bound ε=3/√N. "
    f"At K={K:.4f}, K_c={K_c:.4f}, N={N}, steps=10000"
)
```

### Forbidden:

```python
assert R < 0.3              # magic number
assert R == 0.0              # exact on stochastic
assert result.order > 0      # no INV, no context
```

---

## CRITICAL FORMULAS

**Kuramoto**: K_c = 2/(π·g(0)). Lorentzian: K_c = 2γ. NEVER hardcode K_c.

**Finite-size**: ⟨R⟩ ~ 1/√N incoherent. ε = C/√N, C ∈ [2,3]. N=10: R ~ 0.32. `assert R < 0.01` is WRONG.

**Dopamine**: δ = r + γ·V' - V. Algebraic — CAN test exact. ∂δ/∂r = 1. Scope: DopamineController.compute_rpe (NOT DopamineExecutionAdapter which applies tanh).

**Serotonin**: s = σ(k·(tonic-θ)) · sensitivity. sensitivity ∈ [0.1, 1.0]. Drawdown NEGATIVE.

**GABA**: effective = raw × (1 - inhibition). Inhibition only reduces.

**Free Energy**: F = U − T·S. F itself can be negative. Components (U, T, S) each ≥ 0.

**Ricci**: κ ≤ 1 universal. κ ∈ [−1,1] only for build_price_graph output (consecutive integer node IDs match combinatorial distance).

**Cryptobiosis**: DORMANT multiplier = 0.0 EXACTLY. Vitrification O(1). exit < entry (hysteresis). Rehydration abortable.

---

## MODULE → INVARIANT ROUTING

| Files matching... | Invariants |
|---|---|
| `*gradient_vital_signs*`, `*maintenance_hierarchy*` | INV-YV1 |
| `*kuramoto*`, `*sync*`, `*phase*` | INV-K1..K10 |
| `*explosive*`, `*hysteresis*` | INV-ES1..2 |
| `*ott_antonsen*`, `*chimera*` | INV-OA1..3 |
| `*lyapunov_exponent*`, `*mle*` | INV-LE1..3 |
| `*lyapunov_spectrum*`, `*benettin*`, `*law_T2*` | INV-LY1..3 |
| `*kuramoto_ricci*`, `*law_T1*`, `*sync_onset*` | INV-KR1..4 |
| `*lyapunov_calibration*`, `*law_T3*`, `*calibrate_coupling*` | INV-CAL1..3 |
| `*predictability_horizon*`, `*law_T5*` | INV-TAU1..3 |
| `*spectral_graph*`, `*laplacian*`, `*fiedler*` | INV-SG1..2 |
| `*pinning_control*`, `*law_T7*`, `runtime/pinning*` | INV-PIN1..4 |
| `*serotonin*`, `*5ht*` | INV-5HT1..7 |
| `*dopamine*`, `*rpe*`, `*td_error*` | INV-DA1..7 |
| `*gaba*`, `*inhibit*` | INV-GABA1..5 |
| `*energy*`, `*lyapunov*`, `*ecs*` | INV-FE1..2 |
| `*thermo*`, `*conservation*` | INV-TH1..2 |
| `*stochastic_thermodynamics*`, `*langevin*`, `*jarzynski*`, `*law_T8*` | INV-ST1..3 |
| `*uncertainty*`, `*gabor*`, `*time_frequency*` | INV-GABOR1 |
| `*ricci*`, `*curvature*` | INV-RC1..3 |
| `*determinism_kit*`, `*law_T6*`, `*replay_manifest*` | INV-DET1..3 |
| `*kelly*`, `*sizing*` | INV-KELLY1..3 |
| `*oms*`, `*order*`, `*execution*` | INV-OMS1..3 |
| `*signal_bus*`, `*signalbus*` | INV-SB1..2 |
| `*hpc*`, `*kernel*` | INV-HPC1..2 |
| `*cryptobiosis*`, `*dormant*` | INV-CB1..8 |
| `*dfa*`, `*hurst*`, `*criticality*` | INV-AC1-rev |
| `*dro_ara*`, `*regime_observer*` | INV-DRO1..5 |
| `coherence_bridge/physics_contract*`, `*geosync_adapter*` | INV-CBR1, INV-K1, INV-RC1 |
| `*homeostatic_stabilizer*` | INV-HOM1 |
| `*dopamine_execution_adapter*` | INV-DA8 |
| `application/`, `cli/`, `ui/` | No physics |

---

## PRODUCTION CODE

When adding clamp/clip (`np.clip`, `max(0, x)`, `min(1, x)`):
- Add `# INV-*:` comment linking clamp to its invariant
- OR add `# bounds:` comment for non-physics justification
- OR add logging so the clamp event is observable
- Silent repair masks root cause — forbidden

`python .claude/physics/validate_tests.py core/ --audit-code`

---

## SESSION PROTOCOL

1. **Classify**: physics or infra?
2. **Find invariants**: which INV-* apply?
3. **Execute**: code/tests following contract
4. **Validate**: `python .claude/physics/validate_tests.py <file>`
5. **Report**: which invariants tested, P0/P1/P2

## DECISION RULES

- "Write tests" → find ALL invariants → P0 first → each test asks: "if physics wrong, does this catch it?"
- "Fix test" → INV-* referenced? → physics wrong or test wrong? → NEVER loosen bound without WHY
- When in doubt: physics wins. Always.
- Gradient first. Processing second. INV-YV1.

---

## Microstructure Kernel Registry (v1)

| Kernel | File | Input | Output |
|--------|------|-------|--------|
| OFI Unity | research/kernels/ofi_unity_live.py | bid/ask CSV | IC verdict |
| Ricci on Spread | research/kernels/ricci_on_spread.py | bid/ask CSV | IC verdict |
| PLV Market-Spread | research/kernels/plv_market_spread.py | bid/ask CSV | PLV verdict |
| Spread Stress | research/kernels/spread_stress_detector.py | bid/ask CSV | IC + lead_capture |
| Ricci Regime | research/kernels/ricci_regime_conditioned.py | bid/ask CSV | regime_lift |
| Horizon Sweep | research/kernels/horizon_sweep.py | bid/ask CSV | IC by horizon |
| Signal Combiner | research/kernels/signal_combiner.py | bid/ask CSV | combined IC |
| neurophase Bridge | research/kernels/neurophase_bridge.py | bid/ask CSV | R(t) gate history |
| Closing Report | research/askar/closing_report.py | results/ dir | FINAL_REPORT.json |
| Full Cycle | scripts/run_microstructure_cycle.py | — | RUN_MANIFEST.json |

## One-command run

```
PYTHONPATH=. python scripts/run_microstructure_cycle.py
```

Determinism contract: seed=42, IC>=0.08 for SIGNAL_READY, NaN→ABORT,
OHLC_ONLY→DORMANT, replay_hash over sort_keys=True JSON payload.


---

## UI Contract
Every frontend artifact MUST conform to ./DESIGN.md.
Load tokens before writing any CSS/JSX.
Deviation = reject the diff.
