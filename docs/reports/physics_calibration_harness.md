# Physics-Invariant Calibration Harness

Acceptor: `.claude/commit_acceptors/physics-calibration-harness.yaml`
Module: `core.physics.calibration`
Tests: `tests/unit/physics/test_calibration_harness.py` (21 cases)

## Promise

A one-function-call instrument that lets a developer ask
*"does estimator X still recover known ground truth at the
documented precision?"* and get a self-describing answer.
Engineering-grade simple on the outside, anchored physics on the
inside.

## Public surface

| Symbol | Role |
|---|---|
| `CalibrationReport` | Frozen dataclass; one row per (estimator, ground-truth) pair. Carries INV-ID, truth, estimate, abs-error, spec-tolerance, pass/fail. |
| `calibrate_dro_hurst(H_target, n=4096, seed=42)` | INV-DRO1: generate geometric fBm, run DFA, recover H. |
| `calibrate_ott_antonsen_steady(K, delta, T=100, dt=0.01, R0=0.01)` | INV-OA2: integrate the OA ODE, compare long-time R to analytical √(1−2Δ/K). |
| `run_calibration_suite()` | Run both estimators across the default grid; return dict keyed by INV-* ID. |
| `format_markdown_table(reports)` | Pretty-print a list of reports; suitable for CI artefact emission. |
| `generate_fractional_brownian_motion(H, n, seed)` | Davies & Harte (1987) circulant embedding; exact for H ∈ (0, 1). |
| `python -m core.physics.calibration` | CLI entry; prints the table + pass count. |

## Default-grid result

| INV | Estimator | Cases | Worst error | Tolerance | Pass |
|---|---|---|---|---|---|
| INV-DRO1 | dro_dfa_hurst | H ∈ {0.3, 0.5, 0.7, 0.9} | 0.073 | 0.10 | 4/4 |
| INV-OA2 | ott_antonsen_steady | K/K_c ∈ {1.5, 2, 3, 5, 10} | 1.1e-14 | 1e-3 | 5/5 |

**9/9 pass.** OA2 cases pass at machine epsilon — substantially
tighter than the 1e-3 RK4 envelope. DRO1 cases pass at ~half of
the 0.10 envelope, consistent with the published DFA-Hurst
benchmarks (Couillard & Davison 2005, Weron 2002).

## A finding the harness already produced

While building the harness, the calibration on raw fBm paths
returned errors of 0.16–0.58 — far outside the tolerance. Root
cause: `core.dro_ara.engine.derive_gamma` is calibrated for
**price** input (its first step is `diff(log|x|)`), not for raw
fBm paths that may cross zero. For paths near zero the
``log|x|`` introduces artefacts unrelated to the Hurst exponent.

The fix is **inside the calibration**, not the estimator: feed
``P(t) = exp(fBm_H(t))`` (geometric fBm — the standard
quantitative-finance model for prices). This is documented in the
docstring of :func:`calibrate_dro_hurst` and is a tier-honest
contract: the estimator stays calibrated for prices, the
calibration generates prices.

This is the kind of issue an algebraic identity test (the
``γ = 2H + 1`` invariant) cannot catch — the identity holds
between the ESTIMATED γ and the ESTIMATED H even when both are
wrong. Calibration against ground truth is the orthogonal axis.

## What's *not* changed

* No existing estimator code modified — only the calibration
  layer is new.
* No new dependencies — pure NumPy.
* The fBm generator (Davies & Harte) is reference-grade; for
  ``H = 0.5`` produces fGn whose lag-1 autocorrelation is
  near zero, for ``H > 0.5`` persistent, for ``H < 0.5``
  anti-persistent — all three asserted by tests.

## Quality gates

| Gate | Status |
|---|---|
| `black --check` (2 files) | clean |
| `ruff check` (2 files) | clean |
| `mypy --strict` (2 files) | clean |
| `pytest tests/unit/physics/test_calibration_harness.py` | 21/21 passed |
| `python -m core.physics.calibration` (smoke) | 9/9 passed on default grid |

## Engineer-facing one-liner

```python
from core.physics.calibration import run_calibration_suite, format_markdown_table
suite = run_calibration_suite()
print(format_markdown_table([r for v in suite.values() for r in v]))
```

That is the ecstasy-grade interface: one call, one table,
verdict per row. The physics is anchored to CLAUDE.md
invariants; the synthetic generator is reference-grade; the
tolerances come from the catalog. Nothing decorative.
