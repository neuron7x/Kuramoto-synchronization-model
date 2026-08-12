# NEW_TESTS_MATRIX

File: `tests/unit/core/test_kuramoto_engine_numerical_hardening.py` (11 cases)

| Test | Class | Target | Invariant | Mutant killed |
|---|---|---|---|---|
| `test_rk4_step__dt_halving__converges_at_fourth_order` | metamorphic / numerical-stability | `_rk4_step` | RK4 order p=4 (ratio≈16) | RK4→Euler: order collapses to ~1 → **FAIL** ✓ |
| `test_rk4_step__zero_frequency__is_rotation_equivariant` | metamorphic | `_dtheta_dt`/`_rk4_step` | coupling depends only on phase diffs | sign/offset mutation of `diff` → **FAIL** ✓ |
| `test_kuramoto_result__nonfinite_order_parameter__fails_closed[nan/inf/-inf]` | fail-closed negative | `KuramotoResult` L83 | INV-K1 NaN-leak protection | drop finiteness guard → **FAIL** ✓ |
| `test_kuramoto_result__nonfinite_time__fails_closed[nan/inf/-inf]` | fail-closed negative | `KuramotoResult` L85 | finite time axis | drop guard → no raise → **FAIL** ✓ |
| `test_kuramoto_result__nan_order_parameter_bypasses_range_guard_witness` | mutation-resistance witness | `KuramotoResult` L82-83 | range check cannot catch NaN | documents guard is load-bearing |
| `test_dtheta_dt__overflow_to_nonfinite_rhs__fails_closed` | fail-closed negative | `_dtheta_dt` L271 | finite RHS | drop guard → no raise → **FAIL** ✓ |
| `test_rk4_step__overflow_propagates_fail_closed` | fail-closed negative | `_rk4_step` L271 | overflow surfaces guard | drop guard → **FAIL** ✓ |

## Mutation testing (manual, PHASE 6)

`mutmut` is not configured in-repo (`MUTATION_NOT_RUN.md` rationale). Three
hand-applied mutants on `core/kuramoto/engine.py`, each reverted byte-identical:

1. `return theta + (dt/6)*(k1+2k2+2k3+k4)` → `return theta + dt*k1` (Euler) — **killed** by convergence test.
2. remove `if not np.isfinite(self.order_parameter).all(): raise` — **killed** by non-finite order test.
3. remove `if not np.isfinite(out).all(): raise` in `_dtheta_dt` — **killed** by overflow test.

All new tests: deterministic (seeded `default_rng`), no network, no time oracle,
finite bounded inputs, INV-tagged 5-field error messages per `CLAUDE.md`.
