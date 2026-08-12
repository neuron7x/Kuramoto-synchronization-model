# COVERAGE_BASELINE — Kuramoto numerical core

- **Commit (origin/main):** `a59e5c7e19f6b3e12047e0460d0042d44407b5db`
- **Worktree:** `/home/neuro7/gs-cov-audit` (detached, clean before changes; rogue
  editable install at `/home/neuro7/GeoSync` neutralised by running with
  `PYTHONPATH=<worktree>` and worktree cwd — `core` resolves to the worktree).
- **Tooling:** Python 3.12.3, pytest 8.4.2, coverage 7.13.5, hypothesis 6.140.3.
- **Tests collected (whole repo):** 18 185 across 1 463 files, 0 collection errors.

## Scope decision

A single-process branch-coverage run over all 18 185 tests is not the project
oracle (CI fast-shards are; local single-process is contaminated by jax-env /
xdist flakiness and exceeds the 20-min cap). Baseline was therefore acquired
**risk-first**, scoped to the highest-severity domain: the Kuramoto numerical
core (`core/kuramoto/`), by running every test file that imports
`core.kuramoto` (55 files), deselecting `-m slow`, under
`coverage --branch --source=core/kuramoto`.

## Baseline coverage — `core/kuramoto/` (branch)

| Module | Stmt cov | Missing (lines) | Risk |
|---|---|---|---|
| contracts.py | 98.48% | 283, 290 | CRITICAL (data contract) |
| **engine.py** | **91.19%** | **83, 85, 166, 237, 241, 248, 271** | **CRITICAL (RK4 integrator)** |
| metrics.py | 87.03% | 89,91,93,95,205,416-425,472 | CRITICAL (R, entropy) |
| falsification.py | 56.60% | 135-160,269-293,303-312,324-328,340-343 | CRITICAL (surrogates) |
| kuramoto_ricci_engine.py | 87.88% | 139,142,182,271,273,275 | HIGH |
| network_engine.py | 95.79% | 245, 259 | HIGH |
| ricci_flow_engine.py | 89.13% | (26 lines) | HIGH |
| synthetic.py | 85.94% | 116-132, 295 | MEDIUM |
| jax_engine.py | 27.52% | 53-243 | MEDIUM (optional backend, jax absent) |
| **TOTAL (pkg)** | **84.06%** | — | — |

Note: `metrics.py` / `falsification.py` low residuals are partly an artefact of
`-m slow` deselection (T24/T25 witnesses); they are recorded as **HIGH-residual,
verify-before-claim** in `DEFERRED_COVERAGE.md`, not as confirmed dead code.

## Failed / skipped during baseline run

- **FAILED** `tests/unit/physics/test_T28_wave2_witnesses.py::test_ott_antonsen_unit_disk_bound_property`
  — pre-existing on origin/main. Hypothesis falsifying example `R0≈4.6e-197`
  drives the Ott–Antonsen flow onto the **R=0 incoherent fixed point** (an
  unstable equilibrium of the OA ODE), where the supercritical closed-form
  oracle `√(1−2Δ/K)` does not apply. Classification: **local Hypothesis-DB
  edge / test-strategy boundary**, module `ott_antonsen.py` — OUT OF SCOPE for
  this engine PR; CI runs a fresh Hypothesis DB + deterministic profile and is
  unlikely to reproduce. Recorded, not hidden.
- SKIPPED: schemathesis optional dep; one synthetic-no-edges case.

## Initial risk hypothesis (confirmed)

`engine.py` is the CRITICAL RK4 integrator. Its missing lines are **fail-closed
guards**, and — more importantly — its executed lines hide an **untested
numerical-stability decision**: nothing verifies the integrator is 4th-order. A
silent Euler regression keeps every existing test green. This is the canonical
"statement coverage executes the line but misses the unsafe decision" gap.
