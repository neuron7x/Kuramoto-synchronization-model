# DRO-ARA Regime Observer — Invariant Registry

**Module:** `core/dro_ara/`
**Test modules:** `tests/core/dro_ara/test_invariants.py`, `tests/core/dro_ara/test_falsification.py`
**Catalog entries:** `.claude/physics/INVARIANTS.yaml::dro_ara`,
`physics_contracts/catalog.yaml::dro_ara.*`

The DRO-ARA v7 observer measures the statistical regime of a price series via
DFA-1 Hurst (on log-returns) and a lag-augmented Augmented Dickey–Fuller test
with AIC lag selection. It emits a regime classification and a deterministic
trading signal through a bounded Action Result Acceptor (ARA) loop.

---

## Invariants

| ID | Type | Statement | Priority | Source |
|----|------|-----------|----------|--------|
| **INV-DRO1** | algebraic   | `γ = 2·H + 1` to float precision | P0 | Peng 1994 |
| **INV-DRO2** | universal   | `rs = max(0, 1 − \|γ − 1\|) ∈ [0, 1]`, Lipschitz-1 in γ | P0 | internal |
| **INV-DRO3** | conditional | `regime == INVALID ⇔ (¬stationary ∨ r² < 0.90)` | P0 | Dickey–Fuller 1979 |
| **INV-DRO4** | conditional | `signal == LONG ⇒ regime == CRITICAL ∧ rs > 0.33 ∧ trend ∈ {CONVERGING, STABLE}` | P0 | internal |
| **INV-DRO5** | universal   | NaN/Inf/constant/rank/short input ⇒ `ValueError` (fail-closed) | P0 | internal |
| **INV-DRO6** | conditional | `free_energy > dynamic_free_energy_threshold ⇒ regime == INVALID ∧ signal == REDUCE ∧ rs == 0` | P0 | internal |
| **INV-DRO7** | universal | DRO-ARA internal comparator chronology is allocated by a monotone SHA-256 event chain, not by `3*step_index` arithmetic | P0 | internal |
| **INV-DRO8** | universal | `belief_variance > 0` and `dynamic_free_energy_threshold ∈ [VARIATIONAL_ENERGY_FLOOR, VARIATIONAL_ENERGY_CEILING]` | P0 | internal |
| **INV-DRO9** | universal | Retained DRO-ARA error and variational-energy buffers have length `≤ STABLE_RUNS`; minimum contract length emits finite `free_energy` | P0 | internal |

## Test mapping

| Invariant | Tests                                                                                   |
|-----------|-----------------------------------------------------------------------------------------|
| INV-DRO1  | `test_invariants.py::test_gamma_is_derived_from_H`                                       |
| INV-DRO2  | `test_invariants.py::test_risk_scalar_bounds`, `::test_rs_long_threshold_constant`       |
| INV-DRO3  | `test_invariants.py::test_classify_invalid_when_not_stationary`, `::test_classify_invalid_when_r2_below_gate` |
| INV-DRO4  | `test_falsification.py::test_signal_never_long_on_gbm`; signal logic checked in `test_invariants.py::test_observe_deterministic` |
| INV-DRO5  | `test_invariants.py::test_observe_rejects_nan`, `::test_observe_rejects_inf`, `::test_observe_rejects_constant`, `::test_observe_rejects_too_short`, `::test_observe_rejects_2d` |
| INV-DRO6  | `test_falsification.py::test_free_energy_circuit_breaker_forces_invalid_reduce` |
| INV-DRO7  | `test_falsification.py::test_dro_ara_exposes_dynamic_belief_and_causal_chronology` |
| INV-DRO8  | `test_falsification.py::test_dro_ara_exposes_dynamic_belief_and_causal_chronology` |
| INV-DRO9  | `test_falsification.py::test_dro_ara_minimum_contract_length_has_finite_energy`, `::test_dro_ara_ara_state_keeps_bounded_energy_window` |

## Falsification battery (known-regime sanity checks)

| Synthetic generator          | Expected regime                  | Test                                               |
|------------------------------|----------------------------------|----------------------------------------------------|
| OU mean-reverting            | CRITICAL or TRANSITION           | `test_falsification.py::test_ou_mean_reverting_is_critical` |
| GBM with positive drift      | INVALID (ADF rejects)            | `test_falsification.py::test_gbm_with_drift_is_non_stationary` |
| Pure random walk             | INVALID or TRANSITION            | `test_falsification.py::test_random_walk_is_invalid_or_transition` |
| White noise on price levels  | stationary                       | `test_falsification.py::test_white_noise_prices_are_stationary`    |

## Empirical reality check

Empirical IC measurement on FX hourly (PR #283): pooled best IC = 0.032 at
horizon 4 (CI95 [−0.015, +0.074]) — **below** the GeoSync `SIGNAL_READY` gate
of 0.08. The module therefore ships as a **regime filter** (`core/strategies/
dro_ara_filter.py`), not as a standalone alpha. See
`scripts/research/dro_ara_ic_fx.py` for the reproducible measurement.

## References

- Dickey, D. A., & Fuller, W. A. (1979). *Distribution of the estimators for
  autoregressive time series with a unit root.* JASA 74(366a), 427–431.
- Ng, S., & Perron, P. (2001). *Lag length selection and the construction of
  unit root tests with good size and power.* Econometrica 69(6), 1519–1554.
- Peng, C.-K., Buldyrev, S. V., Havlin, S., Simons, M., Stanley, H. E., &
  Goldberger, A. L. (1994). *Mosaic organization of DNA nucleotides.*
  Phys. Rev. E 49(2), 1685–1689.
- MacKinnon, J. G. (1994). *Approximate asymptotic distribution functions for
  unit-root and cointegration tests.* J. Bus. Econ. Stat. 12(2), 167–176.
