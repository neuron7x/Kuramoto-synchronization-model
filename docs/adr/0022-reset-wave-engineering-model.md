# ADR 0022 — Reset-Wave as Engineering Numerical Model (FACT/MODEL/ANALOGY)

**Status.** Accepted, 2026-05-03.
**Related.**
- [`docs/governance/IERD-PAI-FPS-UX-001.md`](../governance/IERD-PAI-FPS-UX-001.md) §4.2 (lexicon discipline)
- [`docs/adr/0020-ierd-adoption.md`](0020-ierd-adoption.md) (binding standard)
- [`docs/reset_wave_validation_report.md`](../reset_wave_validation_report.md)
- [`docs/reset_wave_critical_centers.md`](../reset_wave_critical_centers.md)
- [`docs/reset_wave_truth_value_function.md`](../reset_wave_truth_value_function.md)
- [`docs/stability_bounds.md`](../stability_bounds.md)
- [`docs/validation/reset_wave_validation_summary.json`](../../docs/validation/reset_wave_validation_summary.json)

---

## Context

The repository now ships a damped phase-synchronization solver — `geosync.neuroeconomics.reset_wave_engine.run_reset_wave` plus the single-step `re_adaptation_to_baseline` method on `NeuroHomeostaticStabilizer`. This is exactly the kind of cross-disciplinary numerical control surface where Yana's audit Q1 ("what is `physics-aligned` vs merely well-written code?") cuts the deepest, because the easy temptation is to lean on neuroscience / thermodynamics / homeostasis vocabulary to inflate the apparent rigour.

The Phase-0 lexicon discipline (IERD §4.2) was designed to prevent exactly that: keep the FACT layer tight (testable numerical invariants on a compact manifold), the MODEL layer honest (it is a relaxation solver), and the ANALOGY layer scoped to research notes (homeostatic / neuro / "reset-wave" language is metaphor only).

## Decision

Adopt a three-tier scope discipline for the reset-wave subsystem and lock it into the claim ledger with a v3 `falsifier` block.

### FACT (ANCHORED tier)

The continuous form `dθ/dt = K · sin(θ* − θ)` and its discrete Euler / RK4-fixed approximation. The phase-alignment potential `V(θ) = mean(1 − cos(Δφ))`. The four numerical invariants:

* **INV-RESET1.** `V(θ) ≥ 0` by construction (`cos ≤ 1`).
* **INV-RESET2.** Inside the empirical stable region `coupling_gain · dt ≤ 0.2`, `V(θ_{t+1}) ≤ V(θ_t)` on every step.
* **INV-RESET3.** `max(|Δφ|) > max_phase_error ⇒ safety_lock`, after which `final_potential == initial_potential` exactly.
* **INV-RESET4.** Same `(node_phases, baseline_phases, ResetWaveConfig)` ⇒ bit-identical `ResetWaveResult`.

These four are gated through the `reset-wave-phase-synchronization` entry in [`docs/CLAIMS.yaml`](../CLAIMS.yaml) with a v3 falsifier block citing `tests/test_reset_wave_physics_laws.py::test_numerical_invariant_2_potential_nonincreasing_under_stable_reset` as the canonical falsifying test.

### MODEL (EXTRAPOLATED tier)

The reset-wave **purpose** statement: "drive a vector of node phases toward a baseline reference, with a fail-closed lock when any phase exceeds `max_phase_error`." This is a numerical relaxation solver. EXTRAPOLATED rather than ANCHORED because the stability claim is empirical (Monte Carlo n=400 on the grid `coupling_gain × dt × convergence_tol × max_phase_error`), not analytically proven for all parameter cells.

### ANALOGY (SPECULATIVE tier, research notes only)

"Homeostatic stabilizer", "neuro reset-wave", "metastable computing" — interpretive metaphor. Forbidden in the README, product docs, API docs, and reports per IERD §2.3. Allowed only in `paper/`, `research/`, `docs/research/` if added in future.

Lexicon enforcement (IERD §4.2 already applied during this PR):

* `serotonin_gain` → `coupling_gain` (the parameter on `re_adaptation_to_baseline`)
* `truth function` → `objective criterion` (header of `docs/reset_wave_truth_value_function.md`)
* `thermodynamic invariant` (literal) → `numerical invariant`
* `energy` (rhetorical) → `phase potential` / `phase-alignment potential` (only `V(θ) = mean(1 − cos)` is exposed, not "thermodynamic energy")

### CI gates that bind the discipline

* `python scripts/ci/check_claims.py` validates the v3 falsifier block on the new claim.
* `python scripts/ci/compute_pai.py` indirectly counts the four `INV-RESET*` invariants if they appear in CLAUDE.md's MODULE → INVARIANT ROUTING table (a Phase-1 follow-up; for now they are PAI-invisible because they are not in the routing table).
* `python scripts/ci/compute_fps_audit.py` confirms test-evidence + artefact-evidence paths exist for the new claim.
* `python scripts/ci/lint_forbidden_terms.py --phase0-strict-subset` ensures the strict surface (README, governance, audit, validation, ADRs in scope) does not regress to forbidden vocabulary.

## Consequences

### Positive

* Yana's Q1 attack surface shrinks specifically for cross-disciplinary code: there is now a documented worked example of how a "neuro / homeostatic" subsystem is allowed in the repo only when the FACT layer is anchored to numerical invariants and the ANALOGY layer is explicitly scoped.
* Q4–Q7 promote from `UNKNOWN` to `EXTRAPOLATED` because reset-wave provides partial evidence for each: a typed contract surface (Q4), a finite supported state set (Q5), a deterministic O(N · steps) cost surface (Q6), and an exhaustive kernel-level edge-case suite (Q7).
* The lexicon mapping `serotonin_gain → coupling_gain` is now demonstrated in real code, not just in the directive, raising the cost of future drift.

### Costs

* The four `INV-RESET*` IDs are not yet in `CLAUDE.md`'s INVARIANT REGISTRY, so they do not contribute to PAI yet. Phase-1 backfill adds them.
* The four `INV-RESET*` falsifier-test references currently bind through one canonical test (`test_numerical_invariant_2_potential_nonincreasing_under_stable_reset`); Phase-1 should bind a separate `test_id` per invariant.
* MODEL tier remains EXTRAPOLATED until an analytical proof of monotone potential decrease in the stable region replaces the Monte Carlo bound. That proof is well-known in the Kuramoto literature and can be cited rather than re-derived; the citation is a Phase-2 deliverable.

### Risks

* If a future maintainer adds genuine thermodynamic / biological claims under the reset-wave umbrella, the strict-subset lint will block them — but only on the curated surface. The default-scope warn-only lint will not catch python-source forbidden terms. Phase-5 lint promotion closes that.

## Alternatives considered

1. **Reject the cross-disciplinary metaphor entirely.** Rejected — the metaphor is useful for research narrative; the discipline is to scope it to ANALOGY tier rather than ban it.
2. **Allow the `serotonin_gain` parameter as legacy.** Rejected — IERD §4.2 lexicon is the whole point; allowing one violation in a flagship module destroys the gate.
3. **Wait until Phase-1 to wire the v3 falsifier.** Rejected — the four `INV-RESET*` invariants are tight enough to write the falsifier today, and doing so demonstrates that schema v3 works on real ANCHORED claims.

## References

* Kuramoto, Y. (1975). *Self-entrainment of a population of coupled non-linear oscillators*.
* Strogatz, S. (2000). *From Kuramoto to Crawford: exploring the onset of synchronization in populations of coupled oscillators*. Physica D 143, 1-20.
* `geosync/neuroeconomics/reset_wave_engine.py` — the implementation.
* `tests/test_reset_wave_*.py` — 32 unit tests + Monte Carlo grid stress.
