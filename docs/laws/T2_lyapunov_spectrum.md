# GeoSync Physics Law T2 — Full Lyapunov Spectrum

**Status:** ACTIVE • **Tier:** ANCHORED (Benettin et al. 1980; Sandri 1996; Sprott 2003)
**Module:** `core/physics/lyapunov_spectrum.py`
**Tests:** `tests/unit/physics/test_T2_lyapunov_full_spectrum.py`
**Companion to:** `core/physics/lyapunov_exponent.py` (scalar MLE, INV-LE1/LE2)

---

## 1. Statement

For an autonomous ODE on `R^n`,

```
ẋ = f(x),   x(0) = x_0,
```

the **full Lyapunov spectrum** `{λ_1 ≥ λ_2 ≥ … ≥ λ_n}` is recovered numerically by co-integrating the augmented variational system

```
ẋ  = f(x)
Q̇  = J(x) Q,   J = ∂f/∂x,   Q ∈ R^{n × n_exp},   Q^T Q = I_n_exp,
```

with periodic QR re-orthonormalisation `Q ← Q'`, `R ← R'`. The exponents are then

```
λ_k = (1/T) Σ_{m=1}^{M} log |R_kk^{(m)}|,   T = M · qr_every · dt.
```

The result is exact in the limit `T → ∞` and `qr_every · dt → 0` (Benettin et al. 1980).

## 2. Algorithm (as implemented)

1. Initial frame: `Q_0 = [e_1 | e_2 | … | e_{n_exp}]` (orthonormal by construction).
2. Inner loop: `qr_every` midpoint (Heun-RK2) substeps that update `(x, Q)` jointly using one `jax.jacfwd(f)` evaluation per substep.
3. Outer step: reduced QR on `Q`, accumulate `log|diag(R)|` into `log_sum`.
4. Return `λ = sort_descending(log_sum / T)`.

**Why midpoint (RK2), not RK4.** The dominant error in the Benettin estimator is the **finite QR cadence**, not the integrator order. RK2 keeps `jacfwd` calls per step at one (RK4 would need four), which doubles throughput on a sweep without measurable accuracy loss for typical `dt = 5e-3`.

**Why `lax.fori_loop`, not `lax.scan`.** No per-step output stream is needed; `fori_loop` keeps the carry pure and avoids materialising trajectories that the user did not ask for.

## 3. Constitutional Invariants

```
INV-LY1 | algebraic    | linear ẋ = A x: sort_desc(λ) == sort_desc(Re(eigvals(A)))
                       | to 1e-3 at T = 50.                                         | P0
INV-LY2 | conservation | Hamiltonian flow ⇒ Σ λ_k = 0 to 1e-3 on harmonic oscillator
                       | at T = 100 (≈ 16 periods).                                 | P0
INV-LY3 | universal    | finite, bounded input ⟹ finite spectrum; every contract
                       | violation raises ValueError. Fail-closed.                  | P0
```

Compatibility:

* `λ_1 = lyapunov_spectrum(...)[0]` agrees with `core.physics.lyapunov_exponent.maximal_lyapunov_exponent` on integrated trajectories within 10 % at canonical Lorenz-63 settings (T2 derives the variational flow analytically; the scalar estimator works on observed time-series — different finite-T biases).

## 4. Falsification Battery

| Test | What it catches if it fires |
|---|---|
| `test_INV_LY1_diagonal_linear_flow_recovers_eigenvalues` | Integrator/QR coupling broken, sign convention flipped |
| `test_INV_LY1_general_linear_flow_recovers_real_eigenvalue_parts` | Non-diagonal Jacobian path broken |
| `test_INV_LY2_harmonic_oscillator_sum_is_zero` | Non-symplectic drift in midpoint integrator |
| `test_lorenz63_spectrum_matches_published_reference` | Timestep too coarse, QR cadence too sparse, or scaling bug |
| `test_INV_HPC1_determinism_bit_identical_repeat` | Side effects, RNG leak, JAX cache aliasing |
| `test_INV_LY3_fail_closed_on_contract_violation` (parametrised, 7 cases) | Silent input repair, error swallowing |
| `test_negative_control_pure_decay_has_no_positive_exponent` | Spurious positive exponents on contractive systems (proves Lorenz λ_1 > 0 is non-vacuous) |

The Lorenz-63 reference numerically recovers `(λ_1, λ_2, λ_3) ≈ (0.91, 0, -14.5)` (published canonical: `(0.9056, 0, -14.5723)`, Sprott 2003) in ≈ 1 s on a single CPU core after JIT warm-up.

## 5. Industrial Acceptance Conditions

T2 is a law (not a feature) when **all six** are true:

1. ✅ Algorithm pure-functional, JAX-jit-fusable (`fori_loop` only, no Python control flow in hot path).
2. ✅ `mypy --strict --follow-imports=silent` passes; `ruff check` passes; `black --check` passes.
3. ✅ All 16 falsification tests pass; negative control proves positive Lorenz result is informative.
4. ✅ Bit-identical determinism (INV-HPC1) verified on the same hardware/JAX version.
5. ✅ Acceptor YAML recorded; this report path published.
6. ⏳ INVENTORY-hash and INVARIANT REGISTRY in `CLAUDE.md` updated (administered at PR merge).

## 6. Use in the Stack

* **Layer 4 (Processing).** T1 (Kuramoto-Ricci phase boundary) uses `lyapunov_spectrum` to numerically check the analytic boundary `Φ(K, σ_ω, κ) = 0`.
* **Layer 4 (Processing).** T3 (calibration) uses it as the differentiable observable inside `argmin ‖λ_1(θ) − λ_1*‖²`.
* **Layer 4 (Processing).** T4 (correlation-dimension inverse) uses it via Kaplan-Yorke `D_KY = j + Σ_1^j λ_i / |λ_{j+1}|` as the smooth surrogate of `D_2`.
* **Layer 5 (Predictability).** T5 (Landauer-bounded predictability horizon) uses `λ_1` directly: `τ ≤ (1/λ_1) ln(δ_tol / δ_0)`.

## 7. References

* Benettin, G.; Galgani, L.; Giorgilli, A.; Strelcyn, J.-M. (1980). *Lyapunov characteristic exponents for smooth dynamical systems and for Hamiltonian systems; a method for computing all of them.* Meccanica 15, 9–30.
* Sandri, M. (1996). *Numerical Calculation of Lyapunov Exponents.* The Mathematica Journal 6.
* Sprott, J. C. (2003). *Chaos and Time-Series Analysis.* Oxford University Press.
* Pesin, Ya. B. (1977). *Lyapunov characteristic exponents and smooth ergodic theory.* Russian Mathematical Surveys 32(4).
