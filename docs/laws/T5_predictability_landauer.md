# GeoSync Physics Law T5 — Landauer-budgeted Predictability Horizon

**Status:** ACTIVE • **Tier:** ANCHORED on Lorenz (1969); Landauer (1961); Bennett (2003)
**Module:** `core/physics/predictability_horizon.py`
**Tests:** `tests/unit/physics/test_T5_predictability_landauer.py`
**Depends on (semantically):** Law T2 (`λ_1` from `lyapunov_spectrum`)

---

## 1. Statement

For an autonomous chaotic flow with maximal Lyapunov exponent `λ_1 > 0`, two infinitesimally close trajectories separate exponentially:

```
|δx(t)|  ≈  |δx(0)| · exp(λ_1 · t).
```

The **predictability horizon** is the time at which the separation reaches an operational tolerance:

```
τ(λ_1; δ_0, δ_tol)  =  (1/λ_1) · ln(δ_tol / δ_0).        (Lorenz 1969)
```

Below `τ`, the trajectory is reproducible to `δ_tol`. Above `τ`, it is not. `λ_1 ≤ 0` ⇒ `τ = +∞` (predictable indefinitely in the operational sense).

Landauer's principle (1961) sets a **physical lower bound** on the energy required to *initialise* the state to precision `δ_0`. For dynamic range `Δ`:

```
E_min(δ_0)  =  k_B · T · ln(Δ / δ_0).                    (Landauer 1961)
```

Inverting under a hard energy budget `E_budget`:

```
δ_0_min(E_budget)  =  Δ · exp(−E_budget / (k_B · T)).
```

The **Landauer-budgeted predictability ceiling** is therefore

```
τ_max(λ_1; E_budget, T, δ_tol, Δ)
    =  (1/λ_1) · [ln(δ_tol / Δ)  +  E_budget / (k_B · T)].
```

This is the operational answer to "how long can I predict, given my energy budget for initialisation?" — and it is a **physical** ceiling, not a software limit.

## 2. Public surface

| Symbol | Role |
|---|---|
| `HorizonReport` | NamedTuple: `tau`, `delta_0`, `delta_0_min_landauer`, `energy_required_J`, `saturated_budget` |
| `predictability_horizon(λ_1, *, δ_0, δ_tol)` | Lorenz horizon; +∞ for λ_1 ≤ 0; fail-closed on bad input |
| `landauer_min_initialisation_energy(δ_0, *, Δ, T)` | `k_B · T · ln(Δ/δ_0)` |
| `landauer_min_initial_precision(E_budget, *, Δ, T)` | inverse: `Δ · exp(−E/(k_B·T))` |
| `predictability_horizon_under_budget(λ_1, *, δ_tol, Δ, E_budget, T, δ_0_request=None)` | master formula; saturates the budget by default |
| `K_BOLTZMANN`, `ROOM_TEMPERATURE` | re-export of physical constants from `core.physics.landauer` |

## 3. Constitutional Invariants (P0)

```
INV-TAU1 | algebraic    | Lorenz: τ(λ_1) = (1/λ_1) · ln(δ_tol/δ_0);     | P0
                       | +∞ for λ_1 ≤ 0. Halves under doubling λ_1.
INV-TAU2 | conservation | Landauer: E_min(δ_0) = k_B·T·ln(Δ/δ_0) exact; | P0
                       | round-trip to 1e-10 in float64-representable
                       | regime (E ≪ 700·k_B·T ≈ 2.9e-18 J at 300 K);
                       | over-budget δ_0_request → ValueError.
INV-TAU3 | universal    | every contract violation → ValueError;        | P0
                       | fail-closed; no silent repair.
```

## 4. Falsification battery (27 tests, all green)

| Test | What it catches if it fires |
|---|---|
| `test_INV_TAU1_horizon_matches_analytic_formula` | Lorenz formula off by 1e-12 |
| `test_INV_TAU1_non_chaotic_returns_infinite_horizon` | λ_1 ≤ 0 sentinel broken |
| `test_INV_TAU1_horizon_scales_inversely_with_lambda` | 1-D scaling violated (algebraic) |
| `test_INV_TAU1_horizon_increases_with_finer_initial_precision` | log-monotonicity broken |
| `test_INV_TAU2_landauer_energy_matches_kT_lnRatio` | Landauer formula off by float-precision |
| `test_INV_TAU2_landauer_min_precision_is_exact_inverse` | δ_0_min ↔ E_min round-trip drifts |
| `test_INV_TAU2_under_budget_returns_finite_tau_at_room_T` | budget saturation broken |
| `test_INV_TAU2_request_below_landauer_floor_raises` | over-budget δ_0 silently accepted (would violate energy conservation) |
| `test_INV_TAU2_explicit_request_at_or_above_floor_accepted` | valid δ_0_request rejected by error |
| `test_INV_TAU3_*` (15 parametrised) | silent input repair on any of 4 functions |
| `test_use_case_room_T_modest_budget_gives_long_horizon` | realistic operating-regime sanity |
| `test_INV_HPC1_pure_function_repeatable` | hidden side effect or non-determinism |

## 5. Industrial acceptance conditions

T5 is a law (not a feature) when **all six** are true:

1. ✅ Pure functional; no JAX dependency at runtime; no I/O; no state.
2. ✅ `mypy --strict --follow-imports=silent` clean; `ruff` clean; `black --check` clean.
3. ✅ All 27 falsification tests pass.
4. ✅ Determinism by construction (pure-functional).
5. ✅ Acceptor YAML recorded; this report path published; INVARIANT REGISTRY updated.
6. ⏳ INVENTORY-hash and module-routing in `CLAUDE.md` updated (administered at PR merge).

## 6. Use in the stack

* Provides the **physical predictability ceiling** for any chaotic GeoSync component. With `λ_1` from Law T2 and a state initialisation budget, T5 returns the tightest `τ` available.
* Layer 0 (Gradient): if `τ_max < t_required` (the time-to-act on a signal), the system is operating past its predictability horizon — the gradient is gone, processing computes noise. Trigger Cryptobiosis (DORMANT).
* Layer 4 (Processing): all signal-emitters publish a `HorizonReport` alongside the signal. Downstream consumers gate on `tau ≥ horizon_required`.
* Composes with T6 (determinism kit, upcoming): bit-identical replay below `τ` is a *physical* property, not just a software guarantee.

## 7. References

* Lorenz, E. N. (1969). *The predictability of a flow which possesses many scales of motion.* Tellus **21**, 289–307.
* Landauer, R. (1961). *Irreversibility and heat generation in the computing process.* IBM J. Res. Dev. **5**, 183–191.
* Bennett, C. H. (2003). *Notes on Landauer's principle, reversible computation, and Maxwell's Demon.* Stud. Hist. Philos. Mod. Phys. **34**, 501–510.
