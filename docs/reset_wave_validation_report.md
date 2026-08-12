# Reset-wave: validation report

> Engineering numerical model — **not** fundamental physics.

## Scope statement (FACT / MODEL / ANALOGY per IERD §4.2)

This subsystem is a **numerical relaxation solver** on the compact phase manifold `[-π, π)`. Phase synchronization is a well-known mathematical structure (Kuramoto 1975, Strogatz 2000); the implementation is a discrete-time application of that structure to internal node-phase reset, **not** a thermodynamic or neurobiological simulator.

* **FACT (ANCHORED).** Implemented ODE / discrete dynamics on the circle:
  `θ_{t+1} = θ_t + dt · coupling_gain · sin(θ* − θ_t)`.
* **MODEL (EXTRAPOLATED).** Damped phase synchronization for reset / re-alignment with fail-closed safety lock.
* **ANALOGY (SPECULATIVE, research notes only).** Neuro / homeostatic language is interpretive metaphor only. Per IERD §4.2: `truth function → objective criterion`, `serotonin_gain → coupling_gain`, `thermodynamic → stability-like` — already applied throughout the implementation.

## Falsifiable claims (per IERD §3)

1. Inside the stable region (`coupling_gain · dt ≤ 0.2`) the bounded phase potential is non-increasing on every step.
2. If any initial absolute phase error exceeds `max_phase_error`, the lock mode fires fail-closed and no active update is performed.
3. Identical input + identical config ⇒ bit-identical output (determinism).
4. The latent forecast layer classifies the trajectory into one of {LOCKED, CONVERGING, DIVERGING, OSCILLATORY, UNSTABLE, UNKNOWN} with bounded confidence in [0, 1].

## Calibration artefacts

* [`docs/validation/reset_wave_validation_summary.json`](validation/reset_wave_validation_summary.json) — Monte Carlo summary (n=400, accuracy=1.0, stable rule = `coupling_gain · dt ≤ 0.2`)
* [`tests/test_reset_wave_stress_validation.py`](../tests/test_reset_wave_stress_validation.py) — 108-cell × 20-seed stress grid; deterministic on seed 20260503, no need to ship a separate sample dump

## Observed metrics

* Monte Carlo scenarios: `n = 400`
* Predictive-layer measured accuracy vs labelling rule: `1.0`
* Stable-region rule used: `coupling_gain * dt <= 0.2`

## Negative / adversarial coverage

* too-large `coupling_gain · dt` → nonconvergence (covered by `tests/test_reset_wave_stress_validation.py::test_negative_nonconvergence_large_dt_gain`)
* `max_phase_error` exceedance → safety lock (covered by `tests/test_reset_wave_physics_laws.py::test_numerical_invariant_4_lock_on_critical_error`)
* phase-wrap boundary at `±π` (covered by `tests/test_reset_wave_physics_laws.py::test_phase_wrapping_and_distance` + `test_phase_alignment_potential_wrap_consistency`)
* deterministic replay (covered by `test_numerical_invariant_5_determinism`)

## Operational interpretation

This component is acceptable as a deterministic **numerical relaxation solver** with explicit bounds and fail-closed safety, **not** a claim of literal thermodynamic, biological, or first-principles physical law.

## Tier label

`tier: ANCHORED for FACT (32/32 tests pass + Monte Carlo n=400 = 100% accuracy + 7/7 critical centers + audit_critical_centers green).`
`tier: EXTRAPOLATED for MODEL (interpretation as damped relaxation; honest within bounded scope).`
`tier: SPECULATIVE for ANALOGY (homeostatic / neuro language is metaphor; lives in research-notes scope only).`
