# Forced-Kuramoto Phase Correction — Real Component

Acceptor: `.claude/commit_acceptors/kuramoto-phase-correction.yaml`
Module: `core.kuramoto.phase_correction`
Tests: `tests/unit/physics/test_kuramoto_phase_correction.py` (18 cases)

## Origin

The user surfaced a candidate diff that proposed a method
`re_adaptation_to_baseline` on `NeuroHomeostaticStabilizer` claiming
to implement a "decentralized reset wave" with "serotonin-gain"
parameter. Audit identified eight class-of-bug problems in the
proposal:

1. **Phase distance non-modular** — `abs(base − node)` ignores the
   `2π` wrap, catastrophic near `±π`.
2. **"reset_energy" mislabel** — `mean(sin(diff))·gain` is the
   Kuramoto sync gradient (velocity), NOT energy. Honest energy
   is `Σ(1 − cos(diff))`.
3. **Trust-me boolean** — `write_ops_inhibited=True` hardcoded,
   regardless of state. Violates `feedback_chronology_discipline`.
4. **Decorative class-name string** — `activation_trigger=
   "NeuroHomeostaticStabilizer"`. Theatre.
5. **Magic tolerance** — `convergence_tol=0.05` without INV-* ref
   or derivation. Forbidden by CLAUDE.md.
6. **Unconnected to instance state** — method takes everything as
   args, doesn't read `self`. So it is a standalone utility, not
   a method on the stabiliser.
7. **`serotonin_gain` decoration** — pure float multiplier with
   no link to `core/neuro/serotonin_*`. Per the operating
   protocol: "don't use 'agent' if no goal/state/memory/action/
   update."
8. **Trivial test fixture** — `[0.98, 1.01, 1.0]` vs three `1.0`s
   gives avg_error ≈ 0.01, well below 0.05 tol. Passes by
   construction. Not falsifying.

## What was salvageable

The kernel is real: forced Kuramoto with a phase reference
``dθ/dt = K · sin(θ_ref − θ)``. Well-defined, well-known
(Kuramoto-Sakaguchi with phase-locked driver). Implementable as
a clean primitive.

## What this PR ships

`core.kuramoto.phase_correction` with **honest math**:

| Symbol | Role |
|---|---|
| `wrap_to_pi(phases)` | Modular fold to `[-π, π]` |
| `circular_phase_distance(a, b)` | Modular distance on the unit circle, output in `[0, π]` |
| `KuramotoCorrectionReport` | Frozen per-step report (velocity_norm, potential_energy, max_phase_error, n_nodes) |
| `KuramotoResetTrajectory` | Frozen multi-step trajectory (final_phases, iterations_run, converged, final_report, potential_history) |
| `kuramoto_correction_step(...)` | Single forced-Kuramoto Euler step toward a reference |
| `reset_to_baseline(...)` | Iterate the step until L∞ residual `< convergence_tol` or `max_iters` exhausted |

## Invariants enforced

* **INV-K-CORR1** (universal, P0): phases in `[-π, π]` after every
  step (modular wrap).
* **INV-K-CORR2** (monotonic, P0): Kuramoto potential
  `V = Σ(1 − cos(θ_ref − θ))` non-increasing under the stability
  bound `K·dt < 2`. Verified across a 76-iter convergence run.
* **INV-K-CORR3** (asymptotic, P1): under the stability bound,
  `max |θ_ref − θ| → 0` exponentially with rate `K`. Hypothesis
  fuzz over `(seed, n, K)` with `dt = 1/(2K)`.

## Negative control (INV-K-CORR2 falsifiability)

`test_reset_negative_control_unstable_bound_can_break_monotonicity`
deliberately pushes past the stability bound (`K·dt = 2.5 > 2`)
and asserts that `V` *can* increase. Without this control, the
monotonicity claim would be unfalsifiable — the bound itself
needs to be testable.

## Differences from the proposed diff

| Aspect | Proposed diff | This PR |
|---|---|---|
| Phase distance | `abs(base − node)` (broken near `±π`) | `wrap_to_pi(base − node)` then `abs` (modular) |
| "Energy" | `mean(sin(diff))·gain` (= velocity) | `Σ(1 − cos(diff))` (honest Kuramoto potential) |
| Velocity | not separated from energy | separate `velocity_norm` field |
| Tolerance | `0.05` magic | `1e-3` documented as 1 milliradian — sub-precision of any production phase estimator |
| Convergence verdict | `avg_error <= tol` | `max_error < tol` (L∞, strictly conservative) |
| `write_ops_inhibited` | hardcoded `True` | not present (caller derives from `converged`) |
| `serotonin_gain` parameter | decorative name | renamed to `coupling` with units of inverse time |
| Where it lives | method on `NeuroHomeostaticStabilizer` | standalone module under `core/kuramoto/` |
| Stability bound | not documented, not tested | documented (`K·dt < 2`), tested with positive *and* negative control |
| Test fixture | trivial pass | random `[-π, π]` initial state + Hypothesis fuzz |

## Quality gates

| Gate | Status |
|---|---|
| `black --check` (2 files) | clean |
| `ruff check` (2 files) | clean |
| `mypy --strict` (2 files) | clean |
| `pytest tests/unit/physics/test_kuramoto_phase_correction.py` | 18/18 passed in 4.7s |

## Composition with existing GeoSync

* The primitive is callable from `geosync.neuroeconomics.homeostatic_stabilizer`
  if a phase-reset is needed, but it is **not bound** to that
  class. The stabiliser's E/I-balance machinery and this
  primitive are orthogonal concerns.
* Composes naturally with the active-inference pack on PR #520:
  the `final_phases` of a `reset_to_baseline` call can serve as
  a `preferred_state` for the variational free energy gradient
  (Task 3 of the FEP roadmap).
