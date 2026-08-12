<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Decision Record — Flagship RQ Selection (RES-001)

- **Date:** 2026-07-19
- **Branch:** `remediation/wave3-p0`
- **Task:** RES-001 — select ONE flagship falsifiable research question; quarantine the rest.
- **Boundary in force:** `RESEARCH_ALPHA`, synthetic-only, `NO_DEPLOY`.

## Problem

GeoSync accumulated dozens of parallel research claims across `research/`,
`research_lines/`, `docs/research/`, `docs/phd/`, and `CLAIMS.md`. Running many
half-open claims in parallel dilutes falsifiability: no single question is being
driven to a preregistered verdict, and the market-structure lines cannot be
honestly closed inside the synthetic-only / `NO_DEPLOY` boundary. Remediation:
promote exactly one honestly-falsifiable question to flagship and park the rest
(without deleting them).

## Decision

**Selected flagship:** `FLAGSHIP-RQ-001` — *Does a clean-archive wheel-contract
check surface latent first-party reproducibility defects that the pre-existing
CI gate suite does not catch?* (see [`RQ.md`](./RQ.md) / [`rq.yaml`](./rq.yaml)).

This is the RQ2-family question from
[`docs/phd/01_research_questions.md`](../../docs/phd/01_research_questions.md).

## Why this RQ

1. **Honestly falsifiable inside the boundary.** It is answerable purely from a
   repository/build artifact (`artifacts/wheel_contract.json`) — no market data,
   no live venue, no out-of-sample edge. It cannot accidentally become a
   market-performance claim, so it respects `PRODUCT_CATEGORY.md` and
   `FORBIDDEN_CLAIMS.md` by construction.
2. **Genuinely supported, not aspirational.** RQ2's affirmative leg is already
   recorded (a clean-archive wheel contract exposed pre-existing latent broken
   imports and a stale-`build/` re-ship defect that no prior gate caught). The
   flagship narrows that to a preregistered, reproducible *marginal-detection*
   estimand with explicit HARD_PASS / HARD_FAIL criteria.
3. **Narrow estimand with a real comparator.** Population is finite and
   enumerable (packaged modules + declared console scripts); the comparator (the
   status-quo gate suite on the same snapshot) is concrete; the outcome is an
   integer/boolean read from an artifact — not a return.
4. **Fail-closed and cheap.** Deterministic, offline, bounded runtime; a
   negative result (`D == 0` or non-reproducible) is a preserved artifact, not a
   soft "partial success."

## Why the others are quarantined (not deleted)

The market-structure and neuromodulation lines (systemic-risk phase-locking,
Ricci microstructure, CTC falsify, D002J/D002K, kernel registry, capital-weighted
Kuramoto, dopamine/TACL/PNCC) are legitimate but **cannot be honestly closed to a
verdict inside the synthetic-only / NO_DEPLOY boundary** this cycle — they require
provenance-audited real data and signed artifacts to promote past `HYPOTHESIS`.
Two of them carry preserved negative results
(`C-RICCI-MICROSTRUCTURE-V1` = `HYPOTHESIS_NOT_SUPPORTED`) that must not be
re-litigated. The adjacent infrastructure RQs (RQ1 claim-governance, RQ3
falsifier-integrity) are honest but only one flagship is promoted per cycle.

All parked lines are referenced — never removed — in
[`quarantine.yaml`](./quarantine.yaml), each with a status, a reason, and a
`path_back`. The underlying artifacts, preregistrations, and negative evidence
stay in the tree untouched.

## Scope-change rule (binding)

The flagship scope, comparator, and success/failure criteria are **frozen** at
the pinned commit. They **cannot change after any holdout / rerun / artifact
reveal** without opening a **new** study with a new `id`. This is encoded as
`scope_change_requires_new_study: true` in `rq.yaml` and enforced socially by
this record. Post-hoc threshold tuning voids the preregistration.

## Consequences

- One question is now driven to a preregistered verdict; the rest are explicitly
  parked, not silently abandoned.
- On promotion past `HYPOTHESIS`, add a `FLAGSHIP-RQ-001` row to `CLAIMS.md`
  backed by a signed `artifacts/wheel_contract.json`.
- The gate `scripts/ci/check_flagship_rq.py` fail-closes if any required field is
  missing from `rq.yaml` or if the quarantine list is empty.
