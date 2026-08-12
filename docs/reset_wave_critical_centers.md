# Reset-wave: 7 critical numerical-system centers

This checklist defines where the implementation can fail and what is enforced before integration. Each center is audited by `audit_critical_centers()` in [`geosync/neuroeconomics/reset_wave_engine.py`](../geosync/neuroeconomics/reset_wave_engine.py).

1. **phase_manifold_wrapping**
   Phases must remain on the compact manifold `[-π, π)`. Implemented via `wrap_phase`; tested in `tests/test_reset_wave_physics_laws.py::test_phase_wrapping_and_distance`.

2. **numerical_stability_region**
   Inside the calibrated stable region (`coupling_gain · dt ≤ 0.2`, see [`docs/stability_bounds.md`](stability_bounds.md)) the phase-alignment potential `V(θ) = mean(1 − cos(Δφ))` must be non-increasing.

3. **fail_closed_lock**
   Any initial absolute phase error exceeding `max_phase_error` must lock the system: no active state updates, `final_potential == initial_potential`.

4. **deterministic_replay**
   Same input vectors and same `ResetWaveConfig` must produce a bit-identical `ResetWaveResult`.

5. **nonconvergence_detection**
   Outside the stability region (`coupling_gain · dt > 0.2`), oscillation or divergence is permitted but must be detectable as `converged == False`.

6. **regime_interpretation_layer**
   `latent_interpretive_forecast_layer` must return one of `LOCKED | CONVERGING | DIVERGING | OSCILLATORY | UNSTABLE | UNKNOWN` with bounded confidence in `[0, 1]`.

7. **contract_validation**
   Invalid vector lengths, empty inputs, non-positive `coupling_gain / dt / steps / max_phase_error`, and unknown integrator names must raise `ValueError` fail-fast.

**Operational hook.** `audit_critical_centers()` returns a tuple of `CriticalCenterAudit(passed=...)` rows. Smoke test: `assert all(a.passed for a in audit_critical_centers())`. Tested in `tests/test_reset_wave_engine.py::test_critical_center_audit_has_seven_passed_centers`.
