# GeoSync Physics Law T1 — Kuramoto-Ricci Sync-Onset Boundary

**Status:** ACTIVE • **Tier:** ANCHORED on Restrepo-Ott-Hunt 2005, Strogatz 2000, Ollivier 2009
**Module:** `core/kuramoto/kuramoto_ricci_engine.py`
**Tests:** `tests/unit/physics/test_T1_kuramoto_ricci_boundary.py`
**Depends on:** Law T2 (`core/physics/lyapunov_spectrum.py`)

---

## 1. Statement

Let `G = (V, E)` be a connected undirected graph on `N = |V|` nodes with edge weights `κ_ij ∈ [-1, 1]` interpreted as Ollivier-Ricci curvatures. Define the *non-negative* sync adjacency

```
A_ij = max(κ_ij, 0),    A_ii = 0,    A symmetric.
```

(Negative curvatures are anti-correlated random walks — they cannot drive synchronisation under the standard Kuramoto coupling. They are zeroed at the API boundary; the audit trail still keeps `κ` traceable.)

The Kuramoto-Ricci dynamics

```
θ̇_i  =  ω_i  +  K · Σ_j A_ij · sin(θ_j − θ_i),       i = 1, …, N,
```

with intrinsic frequencies `ω_i ~ Lorentzian(0, γ)`, undergoes a sync transition at

```
Φ(K, γ, A)  ≜  K · λ_max(A)  −  2 γ,
```

where `λ_max(A)` is the spectral radius of `A`. The boundary `Φ = 0` separates two regimes:

| Regime  | Condition | Asymptotic `⟨R⟩`         |
|---------|-----------|--------------------------|
| Incoherent   | `Φ < 0` | `⟨R⟩ ≤ O(1/√N)`          |
| Synchronised | `Φ > 0` | `⟨R⟩ > 0` (depends on K) |

`R = |⟨e^{iθ}⟩|` is the Kuramoto order parameter (INV-K1: `R ∈ [0, 1]`).

## 2. Why this exact `Φ`

The result is a direct application of **Restrepo, Ott, Hunt (2005), Phys. Rev. E 71, 036151** to the case where edge weights are Ollivier-Ricci curvatures. Their threshold for synchronisation onset on a heterogeneous undirected network with frequency density `g(ω)` is

```
K_c · g(0) · π  ·  λ_max(A)  =  2.
```

For `g(ω) = (γ/π) / (ω² + γ²)` (Lorentzian, half-width γ): `g(0) = 1/(πγ)`, so `K_c = 2γ / λ_max(A)`. Setting `Φ = K · λ_max(A) − 2γ`, the boundary `Φ = 0` is equivalent to `K = K_c`, and the sign of `Φ` determines the regime.

The complete-graph specialisation reproduces the textbook `K_c = 2γ/(N − 1)` (Strogatz 2000).

The Ollivier-Ricci interpretation of `κ_ij` is anchored in Ollivier (2009) and Lin-Lu-Yau (2011); it gives a principled, physically-derived edge weighting (no ad-hoc tuning) and ties Law T1 directly to GeoSync's INV-RC* family (Ricci curvature on price graphs).

## 3. Constitutional Invariants (P0)

```
INV-KR1 | algebraic    | sign(Φ) ⇒ asymptotic ⟨R⟩ regime:                  | P0
                       |   Φ < 0  ⇒  ⟨R⟩ ≤ 1.5 · 3/√N (subcritical);
                       |   Φ > 0  ⇒  ⟨R⟩ > 0.5 (supercritical, K ≥ 4·K_c).
INV-KR2 | qualitative  | variational MLE crosses 0 through Φ = 0:           | P0
                       |   sub-critical: λ_1 > −0.05 (estimated via T2);
                       |   super-critical: λ_1 < 0.15.
INV-KR3 | conservation | with ω_i = 0 (homogeneous limit), the coupling     | P0
                       | potential V(θ) = ½ Σ A_ij (1 − cos(θ_i − θ_j)) is
                       | non-increasing along midpoint trajectories
                       | (max dV ≤ 1e-9 over T=10 on dense ER graph N=32).
```

## 4. Public surface

| Symbol | Role |
|---|---|
| `BoundaryReport` | Frozen NamedTuple: `phi`, `K_c`, `lambda_max_A`, `lorentzian_half_width` |
| `phase_transition_boundary(K, γ, A)` | Returns `BoundaryReport`; fail-closed on contract violations |
| `ricci_to_adjacency(κ)` | Maps signed curvature → non-negative symmetric adjacency |
| `kuramoto_ricci_rhs(ω, A)` | Factory: returns `θ̇ = f(θ; ω, A)` (closure, jit-friendly) |
| `kuramoto_ricci_step(θ, *, dt, ω, A)` | Single midpoint (Heun-RK2) integration step |
| `kuramoto_ricci_trajectory(θ_0, *, dt, n_steps, ω, A)` | Full trajectory via `lax.scan`, shape `(n_steps + 1, N)` |
| `order_parameter(θ)` | `R = |⟨e^{iθ}⟩|` ∈ [0, 1] |
| `coupling_potential(θ, A)` | `V = ½ Σ A_ij (1 − cos(θ_i − θ_j))` ≥ 0 |

## 5. Falsification battery (18 tests, all green)

| Test | What it catches if it fires |
|---|---|
| `test_order_parameter_in_unit_interval` | `R` outside [0, 1] (compat with INV-K1) |
| `test_ricci_to_adjacency_zeros_negative_curvatures` | Negative κ slips through and breaks INV-KR3 |
| `test_phase_transition_boundary_complete_graph` | `K_c` formula divergence on textbook reference |
| `test_phase_transition_boundary_zero_adjacency` | Disconnected null-graph not caught |
| `test_INV_KR3_boundary_fail_closed` (4 cases) | Silent input repair on Φ inputs |
| `test_INV_KR3_boundary_rejects_signed_adjacency` | A with negative entry treated as valid |
| `test_INV_KR1_subcritical_phi_negative_yields_low_R` | Φ < 0 fails to suppress sync |
| `test_INV_KR1_supercritical_phi_positive_yields_high_R` | Φ > 0 fails to lock sync |
| `test_INV_KR3_potential_monotone_under_gradient_flow` | Non-symplectic drift in midpoint integrator |
| `test_INV_KR2_lyapunov_max_negative_in_synchronised_regime` | Synchronised manifold not stable under T2 estimator |
| `test_INV_KR2_lyapunov_max_positive_or_near_zero_at_subcritical_strong_disorder` | Subcritical state mistakenly contractive |
| `test_INV_HPC1_trajectory_bit_identical_repeat` | Trajectory non-determinism |
| `test_INV_HPC1_step_bit_identical_repeat` | Step-level non-determinism |
| `test_negative_control_omega_nonzero_potential_can_increase` | INV-KR3 monotonicity claim is vacuous |
| `test_negative_control_zero_coupling_phases_drift_apart` | K=0 still produces sync somehow |

The two negative controls are essential: they prove the positive claims (Φ < 0 ⇒ low ⟨R⟩, V monotone with ω = 0) are *informative*, not vacuous.

## 6. Industrial acceptance conditions

T1 is a law (not a feature) when **all six** are true:

1. ✅ JAX-pure, jit-fusable; `lax.scan` for trajectories, no Python control flow in hot path.
2. ✅ `mypy --strict --follow-imports=silent` clean; `ruff check` clean; `black --check` clean.
3. ✅ All 18 falsification tests pass; both negative controls fail-as-expected.
4. ✅ Determinism (INV-HPC1) verified at trajectory and step level.
5. ✅ Acceptor YAML recorded; this report path published; INVARIANT REGISTRY updated.
6. ⏳ INVENTORY-hash and module-routing in `CLAUDE.md` updated (administered at PR merge).

## 7. Use in the stack

* **Layer 4 (Processing).** Provides the principled `K_c` for any Ricci-weighted Kuramoto ensemble in GeoSync — no more magic numbers.
* **Layer 4 (Processing) — T3.** Calibration of `(K, ω, κ)` to a target `λ_1` uses T1 RHS as the dynamical system and T2 estimator as the observable.
* **Layer 4 (Processing) — T7.** Pinning control needs the synchronised manifold to exist; Φ > 0 is the necessary condition. The pinning gain margin `λ_2(L + Γ_P) > ε_pin` is then sufficient.
* **Layer 0 (Gradient).** A stable Φ > 0 regime *is* a sustained gradient (INV-YV1). Φ < 0 means the gradient is destroyed by frequency dispersion — the system computes noise.

## 8. References

* Restrepo, J. G.; Ott, E.; Hunt, B. R. (2005). *Onset of synchronization in large networks of coupled oscillators.* Phys. Rev. E **71**, 036151.
* Strogatz, S. H. (2000). *From Kuramoto to Crawford: exploring the onset of synchronization in populations of coupled oscillators.* Physica D **143**, 1–20.
* Ollivier, Y. (2009). *Ricci curvature of Markov chains on metric spaces.* J. Funct. Anal. **256**, 810–864.
* Lin, Y.; Lu, L.; Yau, S.-T. (2011). *Ricci curvature of graphs.* Tohoku Math. J. **63**, 605–627.
