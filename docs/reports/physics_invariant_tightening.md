# Physics-Invariant Tightening — Seven P0 Companions

Acceptor: `.claude/commit_acceptors/physics-invariant-tightening.yaml`
Branch: `feat/physics-invariant-tightening`

## Promise

Seven P0 invariants from CLAUDE.md gain a *companion* test file that
strengthens existing coverage to the strongest practical form:
algebraic exact at machine epsilon, Hypothesis property fuzz over
input space, boundary-bit-pattern identity, or finite-size sweep
with `1/√N` scaling. No production code is touched — every change
is an additive test under `tests/unit/physics/`.

## Tightening per invariant

| INV | File | Existing form | Companion form | Tests |
|---|---|---|---|---|
| **OA2** (algebraic) | `test_T23_ott_antonsen_algebraic.py` | RK4 1e-3 tolerance via integration | Direct evaluation of `_dz_dt` at the analytical fixed point `R_∞ = √(1 − 2Δ/K)`; asserts `|dz/dt| < 1e-13` across 10 parameter cells | 13 |
| **FE1** (monotonic) | `test_T13_free_energy_monotonicity.py` | INV-FE2 components only | Per-decision contract (`allowed ⟹ ΔF ≤ 0` algebraic, contrapositive `rejected ⟹ ΔF > 0` strict, `ΔF == F_after − F_before` to ULP) over 200 random scenarios × 5 seeds | 11 |
| **LE1** (universal) | `test_T22_lyapunov_robustness.py` | 5 hand-picked input families | Adversarial corpus (single huge spike, two-value alternation, linear ramp, near-overflow, bimodal clusters, ±0 mixture, short-minimal) plus Hypothesis fuzz over `(seed, n, dim, tau, scale)` | 9 |
| **RC1** (universal) | `test_T10_ricci_universal_upper_bound.py` | Cycle / complete / path graphs | Hypothesis fuzz over Erdős–Rényi, Watts–Strogatz, Barabási–Albert random graphs; asserts `κ ≤ 1 + 1e-9` on every edge of every connected sample, plus star/path extremal cases | 6 |
| **DRO1** (algebraic) | `test_T_dro1_gamma_algebraic.py` | H-recovery focus | Tightens `γ = 2H + 1` algebraic identity to documented 1e-5 tolerance across 8 random walks, 4 deterministic trends, Hypothesis fuzz over `(seed, n, sigma)` | 14 |
| **CB1** (universal) | `test_T17_cryptobiosis_exact_zero.py` | Single hand-driven path with `==` | Hypothesis fuzz over distress sequences asserting `multiplier == 0.0` AND IEEE-754 byte-pattern identity to canonical `+0.0` (catches `-0.0` and denormals); re-entry after rehydration; 20-tick repeated DORMANT update | 4 |
| **K2** (asymptotic) | `test_T9_kuramoto_finite_size_sweep.py` | Single point `(N=512, K=0.3·K_c)` | Sweep over `(N ∈ {64,128,256}) × (k_ratio ∈ {0.1, 0.3}) × seed ∈ {7, 42}` plus heavy_math `1/√N` scaling test (`R_128 / R_512 ≈ 2`) | 13 |

**Total**: 70 new tests (69 default + 1 heavy_math).

## What's stronger

* **Algebraic vs integration**: OA2 was tested with 1e-3 RK4 tolerance.
  A sign flip in one of the four RHS terms would not be caught at
  that tolerance. The new test catches it at 1e-13.
* **Property vs hand-picked**: LE1 covered five input families. The
  new Hypothesis fuzz spans ~80 randomized scenarios per pytest
  run with widely-varying scales, lengths, and embedding params —
  including pathologies that strain the Rosenstein nearest-neighbor
  algorithm (bimodal zero-distance neighbors, near-overflow
  magnitudes, ±0 sign-bit edge cases).
* **Bit-pattern vs `==`**: CB1 used `multiplier == 0.0`, which
  passes for `-0.0` and denormals. The new test packs to raw
  bytes and asserts canonical `+0.0` exactly. Catches a class of
  bug where downstream BLAS / GPU multiplication semantics would
  diverge.
* **Sweep vs single point**: K2 checked one cell; the new sweep
  exercises the `1/√N` scaling itself and falsifies the floor on
  a 12-cell grid.

## What is *not* changed

* No production code touched.
* No existing tests modified (companions, not replacements).
* No new dependencies added.
* No CI workflow changes — the new tests fall under existing
  `python-fast-tests` (default) and `python-heavy-tests`
  (heavy_math) gates.

## Quality gates

| Gate | Status |
|---|---|
| `black --check` (7 files) | clean |
| `ruff check` (7 files) | clean |
| `mypy --strict` (7 files) | clean |
| `pytest -m "not heavy_math"` | 69/69 passed |
| `pytest -m heavy_math` (scaling test) | 1/1 passed |
| `.claude/physics/validate_tests.py` | 0 L1, 0 L2, 0 L4 issues; 100% physics grounding |

## Falsifier

The acceptor's `falsifier.command` runs the single strongest test —
INV-OA2 fixed-point residual at machine epsilon. A residual above
`1e-13` on any of the 10 parameter cells would prove
`OttAntonsenEngine._dz_dt` has drifted from the formula
`dz/dt = -(Δ + iω₀)z + (K/2)(z̄ − z|z|²)`. The existing 1e-3
integration test would not catch a sign or factor drift;
this one would.
