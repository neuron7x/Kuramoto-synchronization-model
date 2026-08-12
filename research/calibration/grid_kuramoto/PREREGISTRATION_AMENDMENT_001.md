# Pre-Registration Amendment 001 — CALIB-GRID-001 (append-only)

> **Status:** append-only epistemic-integrity amendment. This is a
> **separate superseding layer**. It does **not** edit the frozen
> `PREREGISTRATION.md`, `gates.py`, or any sha-pinned `RESULTS.json`,
> and it changes **no threshold value**. It supersedes — **forward
> only** (lineage #6+) — the *classification* of the two frozen
> `noisy.*` gates: from pass/fail acceptance gates to
> `infeasible_by_construction` zero-bit diagnostics. The single source
> of truth for the machine contract is
> `PREREGISTRATION_AMENDMENT_001.yaml`; this file is the rationale.

## The problem (CG002-proven)

The frozen `noisy.frobenius` (σ=0.02, `≤0.25`) and `noisy.topology_f1`
(σ=0.02, `≥0.90`) gates were pre-registered as if they tested the
estimator. CALIB-GRID-002 (sha-pinned NEGATIVE, merge `e71d1915`,
ledger `d0f89e24341b0995…`) proved they sit at an
**information-theoretically unreachable operating point**:

* the clean `sin(θ_i−θ_j)` coupling regressor has std 0.00244–0.01611;
* the σ=0.02 noise injects std ≈0.0287 into the *same* regressor;
* ⇒ regressor **SNR < 0.6 on every edge** (0.085 on edge (0,2))
  **before any estimator touches the data**.

The coupling signal is below the measurement noise at the frozen
θ₀/record-length. No estimator — differential, integral, or otherwise —
can recover what the σ=0.02 noise has already destroyed:
`P(FAIL) = 1 ∀ estimator`, so the gate carries **H = 0 bits** about
estimator quality. Scored as a pass/fail acceptance gate it makes every
future lineage's `NEGATIVE` saturate to zero information.

## The amendment (classification only)

| Frozen gate | Threshold (UNCHANGED) | Old class | New class |
|---|---|---|---|
| `noisy.frobenius` | `≤ 0.25` | pass/fail acceptance | `infeasible_by_construction` 0-bit diagnostic |
| `noisy.topology_f1` | `≥ 0.90` | pass/fail acceptance | `infeasible_by_construction` 0-bit diagnostic |

The amended gates are still **run** and still **reported** (the metric
remains an informative regressor-floor witness), but they are
**excluded from the overall lineage pass/fail verdict**, which is
computed over the remaining genuine pass/fail gates only. The
forward-only verdict state for an amended gate is
`INFEASIBLE_BY_CONSTRUCTION` — a distinct zero-bit state, **not** PASS,
**not** FAIL.

## Forward-only — the historical record is byte-frozen

This is the **only** behavioural change and it is **forward-only**:

* It applies only to lineage #6+ runs that **explicitly opt into** the
  amendment.
* It does **not** apply to the merged CALIB-GRID-001 / R1 /
  CALIB-GRID-002 sha-pinned `RESULTS.json` — they remain **byte-frozen**
  with their historical `NEGATIVE` + `FAIL` and are **not** recomputed.
* `build_ledger` / `build_r1_ledger` / `build_cg002_ledger` emit the
  **exact historical bytes** when run *without* the amendment flag; the
  existing `*_results_json_matches_committed_artifact` reproduction
  tests pass **unmodified**.

A regression/golden test proves the historical artifacts are **not**
recomputed (their reproduction tests still reproduce the original FAIL
bytes); a new test proves a fresh run *under* the amendment emits
`INFEASIBLE_BY_CONSTRUCTION` for the amended gates and the correct
reduced-gate overall verdict. A no-peek drift test binds the amendment
constants to the substrate. The amendment path is frozen-after-commit
(commit-acceptor `forbidden_paths`).

## Cross-reference

The causal correction this amendment rests on is recorded in
`SUPERSESSIONS.yaml::SUPERSEDE-001` (R1's double-differentiation
attribution falsified by CALIB-GRID-002's class-independent
regressor-floor proof). This amendment reclassifies the *gate*; that
record supersedes the *attribution*. Together they keep the historical
record honest as-is while preventing lineage #6+ from inheriting either
the falsified premise or the zero-information gate.
