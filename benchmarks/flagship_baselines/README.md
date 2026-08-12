<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); SPDX-License-Identifier: MIT -->
# Flagship baseline hierarchy — FLAGSHIP-RQ-001

This directory defines the **baseline hierarchy** for the flagship research
question and the machinery that decides whether the flagship claim beats those
baselines.

- **RQ:** `research/flagship/rq.yaml` (`FLAGSHIP-RQ-001`)
- **Preregistration:** `protocols/flagship_preregistration.yaml` (`FLAGSHIP-PREREG-001`)
- **Boundary:** `RESEARCH_ALPHA_SYNTHETIC_ONLY_NO_DEPLOY`, `domain_kind: infrastructure`

> This is an **infrastructure** question, not a market question. There is **no**
> return / PnL / Sharpe / edge anywhere here. The outcome is an integer defect
> count `D` read from a repository/build artifact.

## The question

> Does a clean-archive wheel-contract check surface latent first-party
> reproducibility defects (packaged modules importing an unpackaged first-party
> namespace → `ModuleNotFoundError` on clean install, plus dead
> `console_scripts` entry points) that the pre-existing CI gate suite does
> **not** catch?

The preregistered decision variable is the **marginal** count
`D_marginal = |flagship_caught \ existing_suite_caught|`, one-sided threshold
`D_marginal ≥ 1`.

## The hierarchy (each baseline maps to the RQ)

| Tier | What it is | Runnable definition | Maps to the RQ as… |
|------|-----------|---------------------|--------------------|
| **NAIVE** | Run nothing / trust green CI | `baseline_naive` → ∅ | The status quo; catches 0 **by construction**. The floor the flagship must beat. |
| **EXISTING_SUITE** | Pre-existing gates (import-linter, unit tests, release probes) resolving imports **in place** | `baseline_existing_suite` → defects whose namespace fails to resolve with repo root on `sys.path` | The prereg **primary null reference** (`nulls.null_reference`). |
| **ABLATED** | Flagship with the **clean-archive step removed** (working-tree dirs treated as shipped — the stale `build/` failure mode) | `baseline_ablated` → defects whose namespace is missing from the working-tree package set | Isolates the **load-bearing** step (`git archive HEAD`). |
| **SHUFFLED** | Permutation / label-shuffle null (fixed seed; namespaces → stdlib tokens) | `baseline_shuffled` → flagship logic on shuffled labels | Confirms detections are **structural**, not indiscriminate flagging. |
| **FLAGSHIP** | Clean-archive wheel contract (`scripts/ci/check_wheel_contract.py`) | `flagship_check` → first-party imports the wheel excludes | The comparator **under test**. |

Data/cost/resources are matched: every comparator operates on the **same**
frozen snapshot-S evidence surface (`artifacts/wheel_contract.json`), offline,
deterministic, in one pass.

## Decision rule (single source of truth)

`baselines.decide(...)` — used by **both** the report generator and the CI gate,
so a report cannot claim a verdict its own numbers do not support:

- **SUPPORTED** iff `D_marginal ≥ prereg_margin` **and** the detected set is
  reproducible across ≥ 2 independent reruns **at the pinned snapshot** **and**
  ≥ 1 detected defect is not flagged by any pre-existing gate.
- **REJECTED** iff `D_marginal == 0` (preserved negative; never rewritten).
- **INSUFFICIENT_EVIDENCE** otherwise (margin met but reproducibility/marginality
  not verified).

## Current result (honest)

`comparison_report.json` (regenerate with `python run_comparison.py`):

- Baselines all catch **D = 0**; flagship catches **D_total = 70**;
  **`D_marginal = 70`** on the committed snapshot-S artifact.
- **Verdict: `INSUFFICIENT_EVIDENCE`** — *not* `SUPPORTED`.

Why not `SUPPORTED`, despite `D_marginal = 70`? The prereg requires the detected
set to be **reproducible across ≥ 2 independent reruns at the pinned snapshot**.
Two independent reruns of the instrument at the current `HEAD` are bit-for-bit
identical (74 == 74), proving the instrument is **deterministic** — but the
committed snapshot-S artifact reports **70** defects with a **different**
`wheel_sha` (it is **stale** relative to `HEAD`), and no same-S rerun was
executed here. The same-S reproducibility leg is therefore unverified, and the
verdict is held at `INSUFFICIENT_EVIDENCE` (fail-closed). **No `SUPPORTED`
result is fabricated.**

To promote to `SUPPORTED`: run `scripts/ci/check_wheel_contract.py` twice at the
pinned commit, confirm the 70-defect set is bit-identical, then set
`REPRODUCIBILITY_VERIFIED_AT_S = True` in `run_comparison.py` and regenerate.

## Files

- `baselines.py` — runnable baseline definitions + the `decide` rule (SSOT).
- `run_comparison.py` — runs all comparators, writes `comparison_report.json`
  (`--check` verifies freshness).
- `hierarchy.yaml` — declarative tier registry (human-facing contract).
- `comparison_report.json` — D per baseline vs flagship + applied verdict.

Validated by `scripts/ci/check_baselines.py`; tested by
`tests/ci/test_baselines.py`.
