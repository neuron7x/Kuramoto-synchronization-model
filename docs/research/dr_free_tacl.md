# DR-FREE — distributionally robust free-energy gate

**Status.** Experimental, opt-in. Pure composition over `tacl.EnergyModel`; the base model is never mutated.

## Implemented files
- `tacl/dr_free.py`
- `tacl/__init__.py` (additive exports)
- `formal/tla/RobustFreeEnergyGate.tla`
- `tests/tacl/test_dr_free.py`

## Formula

Box ambiguity set with per-metric radii `r_m ≥ 0`:

```
m_adv      = m · (1 + r_m)        for each metric m
F_robust   = F(m_adv) ≥ F_nominal = F(m)
```

Equality holds when all radii are zero. The base `EnergyModel.free_energy` is invoked twice (nominal and adversarial) — no internal state is modified.

State classifier (`robust_energy_state`):
- `F_robust ≥ crisis_threshold`  ⇒ `DORMANT`
- `F_robust ≥ warning_threshold` ⇒ `WARNING`
- otherwise                      ⇒ `NORMAL`

## Inputs
- `metrics`: `EnergyMetrics`.
- `ambiguity`: `AmbiguitySet(radii: Mapping[str, float], mode="box")`.
- Optional `base_model: EnergyModel`.

## Outputs
`DRFreeResult(nominal_free_energy, robust_free_energy, internal_energy, entropy, adversarial_metrics, ambiguity_set, robust_margin)`.

## Invariants
- `INV-FE-ROBUST`: `F_robust ≥ F_nominal` for every non-negative radius vector; equality at zero ambiguity; monotone non-decreasing in any single radius; unknown metric names and negative radii are rejected fail-closed; the base `EnergyModel` is never mutated.

## Tests
- `test_robust_free_energy_dominates_nominal`
- `test_zero_ambiguity_equals_nominal`
- `test_monotone_in_radius`
- `test_unknown_metric_rejected`
- `test_negative_radius_rejected`
- `test_adversarial_metrics_are_finite`
- `test_robust_state_warning_and_dormant_thresholds`
- `test_nominal_energy_model_unchanged`
- `test_tla_spec_lint_documents_required_safety_properties`
- `test_dr_free_result_dataclass_invariant`

## TLA specification

`formal/tla/RobustFreeEnergyGate.tla` advertises five safety invariants:

1. `TypeOK`
2. `NominalBounded`
3. `RobustDominatesNominal`
4. `ZeroAmbiguityEqualsNominal`
5. `FailClosedOnMalformedAmbiguity`

A Python lint test asserts the file contains all five names. Running TLC is **not** a CI gate — the spec is documentation evidence.

## Known limitations
- Only the box ambiguity is implemented; KL / Wasserstein balls are not.
- Each metric is treated as penalty-increasing (positive perturbation = worse). This matches the GeoSync `EnergyMetrics` schema where every field is a non-negative penalty.
- Worst-case is computed analytically per metric; there is no inner optimization.
- The classifier uses two scalar thresholds; a hysteresis variant is not provided.

## No-alpha-claim disclaimer
This is a controller-level robustness primitive. It does not constitute a trading signal nor a claim of out-of-sample edge.

## Source anchor
Nature Communications 2025 (s41467-025-67348-6) — DR-FREE robust free-energy minimization.
