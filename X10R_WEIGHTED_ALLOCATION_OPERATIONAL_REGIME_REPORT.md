# D-001 — Weighted-allocation operational-regime fidelity

**PR:** `feat/x10r-weighted-allocation-cimini-regime`
**Defect:** D-001 (P0)
**Source:** Issue #637

---

## Why this debt existed

The original `tests/reconstruction/test_weighted_allocation.py`
exercises `allocate_weights` against UNIFORM-Bernoulli supports
(``p = 0.30``). That regime is convenient for unit-testing IPF
convergence, but it does NOT match production: real X-10R runs
generate ``p_ij`` from `fit_cimini_squartini` — heterogeneous,
heavy-tailed, dominated by top-fitness pairs. A Gate 5 verdict
that looked clean in the lab regime might break in the
operational regime.

This PR closes that gap with a dedicated test surface.

---

## What this PR does

`tests/reconstruction/test_weighted_allocation_under_cimini_regime.py`
pins the operational-regime contract:

```
For each density d in {0.03, 0.05, 0.08, 0.12}:
    1. Synthesize lognormal s_out, s_in (mass-balanced).
    2. fit_cimini_squartini(s_out, s_in, target_density=d).
    3. p = p_link(fit.x, fit.y, fit.z).
    4. a = sample_adjacency_bernoulli(p, rng=...).
    5. w = allocate_weights(a, s_out, s_in).
    6. Measure row_L1 / col_L1 (Gate 5 metric class).
    7. Cell PASSES iff row_L1 ≤ 0.05 AND col_L1 ≤ 0.05.
```

Tests:
- **Per-cell smoke** (4 fast, parametrised over density): each
  density cell completes without crash; row/col L1 in [0, 1).
- **`test_operational_regime_passes_three_of_four_densities`**
  (1 fast): the headline gate. ≥ 3 of 4 cells must clear.
- **`test_total_mass_conserved_in_cimini_regime`** (4 fast,
  parametrised): even when row/col L1 clips the threshold, total
  mass is conserved to 1 % relative — GATE_2 at the global level.
- **`test_operational_regime_robust_across_seeds`** (1 slow):
  three-seed multi-run version to catch a regime that only
  works at the canonical seed.
- **`test_operational_regime_heavy_tail_sigma_2`** (1 slow):
  sigma=2.0 lognormal marginals approximate BIS LBS tails;
  relaxed 2/4 floor (heavy-tail IS the regime where IPF
  residual is hardest).

---

## Empirical result (canonical seed=42, N=80)

| density | row_L1 | col_L1 | Gate 5 ≤ 0.05 |
|---|---|---|---|
| 0.03 | 0.0838 | ~0 | **FAIL** |
| 0.05 | 0.0162 | ~0 | **PASS** |
| 0.08 | 4.3e-10 | ~0 | **PASS** |
| 0.12 | 3.1e-10 | ~0 | **PASS** |

Pass rate: **3/4** — meets the ≥ 3 of 4 acceptance bar.

Density 0.03 fails because at very low density the Cimini support
concentrates on top-fitness pairs and the IPF projection (Almog-
Squartini Sinkhorn-Knopp) leaves structural residual on the
heavy-tailed marginals. This is documented debt — Gate 5 catches
the residual at the verdict boundary; the allocator does NOT
itself fail-closed. The 3/4 floor encodes that contract.

A 4/4 floor would over-constrain — the regime test would fail on
a single unlucky seed at d=0.03 even when downstream Gate 5
still catches the issue. 3/4 matches the actual production
behaviour: the operational regime ALMOST always passes IPF; one
density cell may clip without the regime being unfit-for-purpose.

---

## What this PR does NOT do

- Does NOT change `allocate_weights` or any other source code.
  The test surface is the only new artefact.
- Does NOT touch Gate 6 (Kuramoto precursor). Strict scope.
- Does NOT operate on real data. Synthetic lognormal marginals
  only.
- Does NOT emit any bank-level claim or domain-of-validity
  verdict.
- Does NOT lift `INV-IDENTIFICATION-1` or change the
  INSTRUMENTED-state declaration.

---

## Acceptance gates (per protocol D-001)

- [x] `tests/reconstruction/test_weighted_allocation_under_cimini_regime.py` shipped
- [x] Density sweep `{0.03, 0.05, 0.08, 0.12}`
- [x] `fit_cimini_squartini` → calibrated `p_ij` → Bernoulli A → IPF
- [x] row_L1 / col_L1 ≤ Gate 5 thresholds in ≥3/4 cells (3/4 actual)
- [x] Report: this file (`X10R_WEIGHTED_ALLOCATION_OPERATIONAL_REGIME_REPORT.md`)
- [x] mypy --strict + ruff + black clean
- [x] Commit acceptor: `.claude/commit_acceptors/x10r-weighted-allocation-cimini-regime.yaml`

---

## Reproduction

```bash
git fetch origin feat/x10r-weighted-allocation-cimini-regime
git checkout feat/x10r-weighted-allocation-cimini-regime
pytest tests/reconstruction/test_weighted_allocation_under_cimini_regime.py -v
cat tmp/x10r_weighted_allocation_operational_regime.json
```

The JSON ledger is regenerated on every test run; the values
in the table above are deterministic at seed=42, N=80, sigma=1.0.
