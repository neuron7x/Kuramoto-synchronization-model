# GeoSync Physics Law T3 — Coupling Calibration to a Target λ_1

**Status:** ACTIVE • **Tier:** ANCHORED on Pyragas (1992); Brent (1973)
**Module:** `core/kuramoto/lyapunov_calibration.py`
**Tests:** `tests/unit/physics/test_T3_lyapunov_calibration.py`
**Depends on:** Law T1 (`kuramoto_ricci_rhs`), Law T2 (`lyapunov_spectrum`)

---

## 1. Statement

For a fixed Kuramoto-Ricci network `(ω, A_κ)` and a requested maximal Lyapunov exponent `λ_target`, find

```
K*  =  argmin_{K ∈ [K_min, K_max]}  |λ_1(K · A_κ; ω)  −  λ_target|²,
```

where `λ_1` is the leading exponent computed by Law T2 from the variational flow of `kuramoto_ricci_rhs(ω, K · A_κ)`.

**Why one scalar, not a vector.** The Kuramoto-Ricci kernel has exactly one tunable scalar (`K`) that monotonically scales the spectral profile while preserving topology and the intrinsic-frequency distribution. Calibrating *all* of `(K, ω, κ)` jointly is **not** a well-posed inverse problem — multiple parameter vectors produce identical `λ_1` (e.g. in the supercritical regime `λ_1 ≈ 0` is achieved across a broad K-range). T3 ships only the well-posed slice; the joint inverse is rejected by design.

**Why gradient-free.** SciPy's bounded Brent minimiser converges in ~10–30 evaluations on a smooth 1-D objective. Backpropagating through a 4 000-step `fori_loop` of Jacobians via `jax.grad` is technically possible but wasteful for a 1-D search.

## 2. Algorithm

1. Validate contracts (positivity, shapes, finiteness). Fail-closed on any violation.
2. Define the closure `objective(K) = (λ_1(K · A; ω) − λ_target)²`.
3. Call `scipy.optimize.minimize_scalar(objective, bounds=(K_min, K_max), method='bounded')`.
4. Re-evaluate `λ_1(K*)` to obtain the achieved exponent.
5. If `|λ_achieved − λ_target| ≤ tolerance` → `CONVERGED`; else → `INFEASIBLE`.
6. Return `CalibrationReport(status, K_optimal, lambda_achieved, residual, n_evaluations)`.

The optimiser is deterministic (Brent's method on the same objective evaluates the same points), so identical inputs yield bit-identical `K*` (INV-HPC1 compatibility).

## 3. Constitutional Invariants (P0)

```
INV-CAL1 | algebraic    | feasible target ⇒ residual ≤ tolerance        | P0
                       | (default 5e-2). Round-trip from synthesised
                       | λ via K_truth: residual typically 1e-12.
INV-CAL2 | conditional  | infeasible target ⇒ status INFEASIBLE,        | P0
                       | never silent best-effort. Tested with λ = 5.0
                       | on a small synced graph (physically unreachable).
INV-CAL3 | universal    | K* > 0 always; hard search bound (K_min > 0    | P0
                       | enforced), no soft penalty. Every contract
                       | violation raises ValueError; fail-closed.
```

## 3.1 Corollary T3.1 — supercritical λ₁-invariance ⇒ inverse non-injectivity

```
Corollary T3.1 | algebraic | K > K_c ⇒ λ₁(K·A_κ; ω) is constant in K to    | P1
                           | machine precision. The λ→K inverse is therefore
                           | a constant-to-interval map (non-injective). The
                           | calibrator's promise is on the λ-residual, never
                           | on K-recovery. A THEOREM derived from Laws T1+T2,
                           | not a new constitutional invariant (count stays 97).
         Tests:  tests/unit/physics/test_T3_noninjectivity.py
```

**Statement.** Above the synchronisation threshold the network phase-locks. On
that branch the leading Lyapunov exponent is the slowest *transverse* exponent of
the locked manifold, fixed by the intrinsic-frequency dispersion of `ω`; the
coupling term contributes a sign-definite, K-scaled Hessian that shifts the bulk
spectrum but **leaves λ₁ stationary**. Hence `λ₁(K·A_κ; ω) ≡ const` for `K > K_c`.

**Constructive witness (deterministic, x64).** For the canonical battery fixture
(`n=4`, Lorentzian `ω`, `γ=0.5`, `seed=15`):

| K / K_c | K | λ₁ |
|---|---|---|
| 3.0 | 1.0000 | −1.1552453009e-02 |
| 5.0 | 1.6667 | −1.1552453009e-02 |
| 8.0 | 2.6667 | −1.1552453009e-02 |

Across a `2.67×` coupling span the spread in λ₁ is `≈ 4e-17` (≈ 2 ULP at 1e-2).
Three couplings, one exponent: `λ→K` is non-injective **by physics**, not by
numerical noise.

**Consequence (and why this is a law, not a bug).** A calibration asked for the
plateau value returns *some* `K` in the degenerate interval, `CONVERGED`, with a
λ-residual at tolerance — exactly the T3 contract. Any test that demanded the
recovered `K`'s from two supercritical targets to *differ* was asserting a
quantity the dynamics forbid; its historical CI fragility was this corollary
announcing itself. INV-CAL4 turns that surprise into a guarded, falsifiable
statement: should λ₁ ever become K-dependent on the locked branch, the battery
fires and Law T3 must be re-derived.

## 4. Public surface

| Symbol | Role |
|---|---|
| `CalibrationStatus` | Enum: `CONVERGED` or `INFEASIBLE` |
| `CalibrationReport` | NamedTuple: `status`, `K_optimal`, `lambda_achieved`, `residual`, `n_evaluations` |
| `calibrate_coupling_to_lambda(...)` | The calibration entry point |

## 5. Falsification battery (15 tests, 100 % green)

| Test | What it catches if it fires |
|---|---|
| `test_INV_CAL1_recovers_known_K_for_synthetic_target` | Residual exceeds tolerance on a known-feasible target |
| `test_INV_CAL2_infeasible_target_returns_infeasible` | INFEASIBLE not raised on impossible target |
| `test_INV_CAL3_K_optimal_strictly_positive_on_negative_target` | Positivity bound bypassed |
| `test_INV_CAL3_fail_closed_on_contract_violation` (8 parametrised) | Silent input repair |
| `test_INV_CAL3_rejects_signed_adjacency` | Negative κ slips through |
| `test_INV_CAL3_rejects_shape_mismatch` | (ω, A) dimension mismatch silently accepted |
| `test_INV_HPC1_calibration_repeatable` | K* not bit-equal across two identical runs |
| `test_negative_control_K_search_does_not_clamp_to_K_min` | Optimiser silently clamping to K_min on every target — proves the calibration is not vacuous |

The negative control is essential: if the optimiser had a sign bug and always returned `K_min`, every CONVERGED status would still pass INV-CAL1 vacuously. The control asks for two distinct feasible targets and asserts the K* values differ.

## 6. Industrial acceptance conditions

T3 is a law (not a feature) when **all six** are true:

1. ✅ Composes T1 + T2 cleanly; no duplicate physics; no shadow optimisers.
2. ✅ `mypy --strict --follow-imports=silent` clean; `ruff` clean; `black --check` clean.
3. ✅ All 15 falsification tests pass; negative control proves convergence is non-vacuous.
4. ✅ Determinism (INV-HPC1) verified; SciPy + JAX combination is reproducible.
5. ✅ Acceptor YAML recorded; this report path published; INVARIANT REGISTRY updated.
6. ⏳ INVENTORY-hash and module-routing in `CLAUDE.md` updated (administered at PR merge).

## 7. Use in the stack

* Provides the operational answer to "what `K` do I need so that the regime achieves a target Lyapunov profile?" — the GeoSync layer-0/4 control knob is now physically calibrated, not magic.
* T7 (pinning control) will use a CONVERGED `K*` as the prerequisite coupling before activating pinning gains.
* Any production change to `K` in a Ricci-weighted ensemble flows through T3 and emits a `CalibrationReport` artefact (status, residual). No CalibrationReport, no production change.

## 8. References

* Pyragas, K. (1992). *Continuous control of chaos by self-controlling feedback.* Physics Letters A **170**, 421–428.
* Brent, R. P. (1973). *Algorithms for Minimization Without Derivatives.* Prentice-Hall — bounded scalar optimiser used internally by SciPy.
* Restrepo, J. G.; Ott, E.; Hunt, B. R. (2005). *Onset of synchronization …* Phys. Rev. E **71**, 036151 — provides the K_c on which the calibrator's bounded interval is anchored.
