# Digital Free Energy & Active Inference — 7-task pack

Acceptor: `.claude/commit_acceptors/free-energy-active-inference.yaml`
Branch: `feat/free-energy-active-inference`

## Promise

Implement the digital substrate of Friston's Free Energy Principle
in GeoSync as the **homeostatic-survival mechanism** for any
state-bearing agent in the stack. Goal: minimise variational free
energy `F = D_KL[q || p] − E_q[log p(s | z)]` to keep the agent's
posterior in the viable manifold.

## What this PR ships (tasks 1–2 done, 3–7 scaffolded)

### ✅ Task 1 — Variational FE primitive

`core.physics.free_energy_variational`

* `GaussianBelief(mean, log_variance)` — frozen univariate belief
* `DiagonalGaussianBelief(mean, log_variance)` — multivariate diagonal
* `kl_divergence(q, p)` — closed-form KL between two Gaussians
* `kl_divergence_diagonal(q, p)` — sum of per-dimension KLs
* `expected_log_likelihood(q, observation, ...)` — `E_q[log p(s|z)]`
* `variational_free_energy(q, p, observation, ...)` — full F

Pure NumPy. No hidden state. Closed-form. Algebraic exact at 1e-12
on identity cases.

### ✅ Task 2 — Surprise observable

`surprise(observation, predicted_mean, predicted_log_variance)`

Per-tick `−log p(s)` under a Gaussian predictive. Always
non-negative; minimum at `observation == mean` equals the
log-partition `0.5·log(2π·σ²)`. The agent's perceptual loop
minimises this scalar by belief update or action.

22 tests passing (12 algebraic-exact + 6 property/Hypothesis +
4 boundary).

### ⚠️ Task 3 — Preferred-state encoder (next commit, scaffolded)

`core.physics.preferred_state` — encode a Gaussian over the
critical-regime manifold `(R ≈ R_critical, H ≈ 0.5, MLE ≈ 0)`.
Surprise distance = `−log p_pref(observation)` becomes the
**homeostatic-deviation** metric. Edge of chaos as preferred state
of the agent's belief.

* File: `core/physics/preferred_state.py`
* Function: `homeostatic_surprise(observation: NDArray, manifold: PreferredManifold) -> float`
* Test: at `(R_critical, 0.5, 0.0)` surprise = manifold-floor;
  perturbations grow surprise quadratically in Mahalanobis distance.

### ⚠️ Task 4 — Active-inference action selection (next commit, scaffolded)

`core.physics.active_inference_policy` — `argmin_a E[F(s_t+1 | a)]`
over a finite candidate-action set. The expected-future-F
calculation requires:

* a forward-prediction model `p(s_t+1 | s_t, a)`
* a candidate action set
* a roll-out horizon

* File: `core/physics/active_inference_policy.py`
* Function: `select_action(belief, candidates, transition_model, horizon) -> int`
* Test: with two candidates where one predictably reduces F and
  the other increases F, the selector must pick the F-reducing one
  in 100/100 seeded trials.

### ⚠️ Task 5 — Hierarchical two-loop FEP (next commit, scaffolded)

* File: `core/physics/hierarchical_fep.py`
* Two layers:
  - **Fast loop**: per-tick belief update (perceptual mode)
  - **Slow loop**: regime belief (active mode)
* Critical contract: slow loop's prior parameterises the fast
  loop's likelihood. Slow loop's update fires only when
  fast-loop F sustains above threshold for ≥ N consecutive ticks.

### ⚠️ Task 6 — FEP calibration entry (next commit, scaffolded)

* File: `core/physics/calibration.py` (extends PR #518's harness)
* Function: `calibrate_kl_divergence(target_kl: float, ...) -> CalibrationReport`
* Generates two Gaussian beliefs whose analytical KL is
  prescribed; runs `kl_divergence`; reports recovery to 1e-12
  (algebraic) plus a finite-sample MC variant for cross-check.

### ⚠️ Task 7 — F-descent integration witness (next commit, scaffolded)

* File: `tests/integration/test_fep_homeostatic_descent.py`
* 1-D agent in a perturbed environment. Initial belief far from
  the preferred manifold. Apply belief-update rule
  `μ_q ← μ_q − η · ∂F/∂μ_q`. Assert: after 50 steps, F
  monotonically descended (allowing ULP slack), and the agent's
  belief is within 1σ of the preferred manifold.
* Falsifier: random-belief baseline (no F descent) — should
  remain ≥ 5σ from manifold.

## Composition with existing GeoSync

The full digital-FEP loop for a GeoSync agent is:

```
                                     +------------------+
                                     | Preferred state  |
                                     | (Task 3)         |
                                     +--------+---------+
                                              |  p(z)
                                              v
+----------+   observation    +-------------+ q(z) <-- Task 5 slow loop
| Market   | ---------------> | Belief q(z) | -------------------------+
| signals  |                  +-------+-----+                          |
+----------+                          |                                |
                                      |  surprise (Task 2)             |
                                      v                                |
                              +---------------+                        |
                              | F = KL − ELL  | <-- Task 1             |
                              +-------+-------+                        |
                                      |                                |
                                      v                                |
                              +---------------+                        |
                              | argmin_a F    | <-- Task 4             |
                              +-------+-------+                        |
                                      |                                |
                                      v                                |
                              +---------------+                        |
                              | Action policy | -----------------------+
                              | (RebusGate,   |   feedback to belief
                              |  Cryptobiosis)|
                              +---------------+
```

This composes with the existing fail-closed Layer 2 sustainer
(`core.neuro.epistemic_validation` from PR #495) — when F sustains
above the critical threshold, RebusGate emergency_exit fires; when
it sustains far below, the system has homeostatic balance and
trades.

## Quality gates (Task 1–2)

| Gate | Status |
|---|---|
| `black --check` (2 files) | clean |
| `ruff check` (2 files) | clean |
| `mypy --strict` (2 files) | clean |
| `pytest tests/unit/physics/test_free_energy_variational.py` | 22/22 passed |

## Tier honesty

* Tasks 1, 2 — **ANCHORED**, fully shipped, 22 tests, machine-epsilon algebraic
* Tasks 3, 6 — **ANCHORED**, mechanically straightforward (≤ 1 day each)
* Tasks 4, 5 — **EXTRAPOLATED**, design decisions involved (transition model, hierarchy depth)
* Task 7 — **EXTRAPOLATED**, integration; passes only if Tasks 1–6 compose right

Total wall-clock if all 7 ship: ~2 weeks focused work. This PR
ships the 2 load-bearing primitives that the rest depends on.

## Reference

* Friston, K. (2010). The free-energy principle: a unified brain
  theory? *Nature Reviews Neuroscience*, 11(2), 127–138.
* Buckley et al. (2017). The free energy principle for action and
  perception: a mathematical review. *J. Math. Psychol.*, 81,
  55–79.
* Parr, Pezzulo, Friston (2022). *Active Inference*. MIT Press.
