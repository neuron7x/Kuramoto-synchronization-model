<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Flagship Research Question — FLAGSHIP-RQ-001

> **Single flagship, preregistered.** GeoSync carries dozens of parallel
> research claims (see `research/flagship/quarantine.yaml`). Exactly one is
> promoted to *flagship* status here; the rest are quarantined/parked, not
> deleted. The machine-readable source of truth for this question is
> [`rq.yaml`](./rq.yaml); this document is its human-readable mirror and MUST
> stay consistent with it.

**Boundary:** `RESEARCH_ALPHA`, synthetic-only, `NO_DEPLOY`. This is an
*infrastructure* question, answerable from repository evidence (files, wheel
build, CI runs, artifacts). It is **not** a market-performance / alpha / edge
question. See [`PRODUCT_CATEGORY.md`](../../PRODUCT_CATEGORY.md) and
[`FORBIDDEN_CLAIMS.md`](../../FORBIDDEN_CLAIMS.md).

## Question (one line)

Does building the distributable wheel from a clean `git archive HEAD` and
statically resolving its first-party imports and console entry points surface
latent reproducibility defects on a frozen repo snapshot that the pre-existing
CI gate suite does not catch?

## Preregistered fields

- **estimand** — The count `D` of distinct latent first-party defects
  (unpackaged-namespace imports that raise `ModuleNotFoundError` on clean
  install, plus dead `console_scripts` entry points) surfaced **only** by the
  clean-archive wheel-contract check on the frozen snapshot `S`, and **not**
  already flagged by any pre-existing CI gate on the same snapshot. This is
  *marginal* detection, not total.

- **population** — All first-party modules packaged into the wheel built from
  `git archive HEAD` at the pinned commit, plus every `console_scripts` entry
  point declared in that wheel's packaging metadata. A finite, enumerable
  repository artifact. No market data, no external universe, no sampling.

- **intervention** — Build the wheel from a clean `git archive HEAD` (defeating
  any stale local `build/`), statically resolve each packaged module's
  first-party imports and each declared console entry point, and emit
  `artifacts/wheel_contract.json`. Instrument:
  `scripts/ci/check_wheel_contract.py`.

- **comparator** — The pre-existing CI gate suite (import-linter, unit tests,
  standard release-gate probes) run against the **same** frozen snapshot `S`,
  which does not build from a clean archive and does not statically resolve
  packaged-wheel imports.

- **outcome** — Primary: `D`, defects detected only by the wheel contract.
  Secondary: reproducibility of the detected set across independent reruns.
  Both are integer/boolean observables read from `artifacts/wheel_contract.json`
  — neither is a return, PnL, or asserted edge.

- **constraints** — Single machine, offline (no network, no market/live data).
  Deterministic: fixed commit SHA, no wall-clock dependence, reruns reproduce
  the defect set. Bounded runtime (one wheel build + static scan). Commit pinned
  and recorded **before** any rerun/holdout reveal. No source edits between the
  comparator and intervention runs.

- **success_criteria** — `HARD_PASS` iff **all** hold on the pinned snapshot:
  (1) `D >= 1`; (2) the detected defect set is reproducible (identical across
  `>= 2` independent reruns); and (3) at least one detected defect is **not**
  flagged by any pre-existing gate (genuine marginal detection).

- **failure_criteria** — `HARD_FAIL` if **any** hold: (a) `D == 0`; (b) the
  detected defect set is non-reproducible across reruns; or (c) every "detected"
  defect is already flagged by a pre-existing gate (zero marginal detection). A
  `HARD_FAIL` is a preserved negative result
  (`governance/NEGATIVE_EVIDENCE.yaml`), never rewritten into partial success.

## Scope lock (preregistration)

The scope, comparator, and success/failure criteria above are **frozen** at the
pinned commit. They **cannot change after any holdout, rerun, or artifact
reveal** without opening a **new** study with a new `id`. Post-hoc threshold
tuning invalidates the preregistration. (`scope_change_requires_new_study: true`
in `rq.yaml`.)

## Honesty note

This question stays entirely within the synthetic-only / `NO_DEPLOY` boundary.
It makes **no** empirical market claim, asserts **no** out-of-sample edge, and
is falsifiable purely from repository/build artifacts. Its evidence tier is
`HYPOTHESIS`; promotion requires a signed artifact per `CLAIMS.md`, which is not
asserted here.

## See also

- [`DECISION_RECORD.md`](./DECISION_RECORD.md) — why this RQ, why the others are
  quarantined.
- [`quarantine.yaml`](./quarantine.yaml) — the parked/archived parallel claims.
- Gate: `scripts/ci/check_flagship_rq.py` — fail-closed field + quarantine check.
