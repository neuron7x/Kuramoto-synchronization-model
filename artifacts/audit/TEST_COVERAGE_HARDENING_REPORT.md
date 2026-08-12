# TEST_COVERAGE_HARDENING_REPORT — Kuramoto RK4 integrator

Commit baseline: `a59e5c7e` (origin/main). Scope: CRITICAL numerical core
`core/kuramoto/engine.py`. This is the first focused increment of the audit
charter (remaining scopes in `DEFERRED_COVERAGE.md`).

## Coverage delta

| Metric | Baseline | After |
|---|---|---|
| engine.py statement+branch | 91.19% (7 missing) | **94.97%** (4 missing) |
| Lines closed | — | 83, 85, 271 |
| Lines deferred (defence-in-depth, unreachable via public contract) | — | 166, 237, 241, 248 |

## What was hardened

1. **RK4 4th-order convergence** — previously *executed but unverified*. A silent
   Euler regression would pass every existing test; the new Richardson test
   rejects it (order band [3.5, 4.5]; measured 4.02). This is the headline
   "coverage-is-telemetry-not-truth" closure.
2. **INV-K1 NaN-leak guard** — a `NaN` order parameter slips past the `[0,1]`
   range check (NaN comparisons are False). The dedicated finiteness guard
   (engine.py:83) was the only barrier and was untested; now pinned, with a
   mutation-resistance witness documenting why it is load-bearing.
3. **Fail-closed finiteness** on `time` axis and on the RHS evaluator (overflow).

## Critical / high symbols closed

- CRITICAL `_rk4_step` numerical-stability decision — closed.
- CRITICAL `KuramotoResult` non-finite `order_parameter`/`time` — closed.
- CRITICAL `_dtheta_dt` non-finite RHS — closed.

## Methods used

branch coverage · metamorphic testing (Richardson order, rotation equivariance)
· fail-closed negative testing · manual mutation resistance (3/3 mutants killed).

## Bugs found

None. The production guards are correct; the gap was **test adequacy**, not a
runtime defect. No runtime code changed (engine.py restored byte-identical after
mutation probes). Pre-existing unrelated failure recorded (T28 OA edge).

## Gates

- new tests: 11 passed, deterministic.
- mypy --strict: clean. ruff/ruff-format/black: clean (tests config-excluded in CI; verified off-exclude).
- mutation: 3/3 killed.

## Failures remaining

- `test_T28 ott_antonsen_unit_disk_bound_property` — pre-existing, out of scope,
  local Hypothesis-DB edge (see DEFERRED_COVERAGE.md).

## Next smallest PR scope

`falsification.py` — first verify the 56.6% residual is real (not `-m slow`
deselection) by running the T25 surrogate suite unfiltered; then harden the
counterfactual functions (`counterfactual_hub_removal`/`zero_inhibition`/
`zero_delays`).

FINAL_STATUS: CRITICAL_COVERAGE_CLOSED_HIGH_REMAINS
