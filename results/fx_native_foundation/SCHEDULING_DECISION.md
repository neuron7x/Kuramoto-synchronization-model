# FX-native foundation · scheduling decision (MODE_A terminal)

**Mode used:** `MODE_A_PRE_DEMO` (per §2.P2 — demo-critical work is
open, so the protocol's own default selects this mode).

**Terminal decision: `DEFER_UNTIL_POST_DEMO`** (one of the two
MODE_A-admissible labels per addendum A6; the other is
`ESCALATE_TO_OWNER`).

Coupled content recommendation to Yaroslav for the post-defer
trajectory: resume effort on the cross-asset Kuramoto line (see
`KURAMOTO_RELATION.md#K4`). This is a *content recommendation*, not a
separate gate option — the human gate itself presents only the two
MODE_A labels (see `HUMAN_GATE_MEMO.md`).

## Decision criteria applied

| criterion | evidence | outcome |
|---|---|---|
| §2.P0 — existing critical path remains priority | memory `project_demo_deadline.md`: all 4 repos must be 100 % production-ready for demo; `project_xai_submission.md`: xAI application pack active; cross-asset Kuramoto live paper day 11/90 | critical path open |
| §2.P2 — MODE_A only while demo-critical is open | true (above) | MODE_A |
| §2.P3 — FULL mode requires explicit deprioritisation | no such directive in current protocol | FULL blocked |
| §3 data contract resolvable | all 8 files + data_root pinned from `universe.json` / `panel_audit.json` | passed |
| §4 DRO-ARA dependency | MODE_A deliverables are `INDEPENDENT_OF_DRO_ARA` | passed |
| §5 Kuramoto relation | cross-asset Kuramoto ships Sharpe +1.262 OOS on cross-asset panel; Track-A equities-only was MARGINAL; 8-FX Kuramoto not yet run but is the correct empirical floor-test | DEFER |
| §K3 displacement of higher-ROI work | yes, multi-day FX-native workstream displaces demo polish + PR #203 promotion path | SUPPORTED |

## Wall-clock budget used

MODE_A cap: 60–90 min. Actual: within budget (docs only; no data
processing, no signal runs, no diagnostics).

## What MODE_A explicitly did NOT do (fail-closed guardrails)

- did not revive combo_v1 on FX in any form
- did not run substrate diagnostics (reserved for MODE_B)
- did not produce a `mechanism brief`, `candidate families memo`, or
  `prereg skeleton`
- did not build any null / baseline infrastructure
- did not guess data paths
- did not change the closure state of `combo_v1_fx_wave1`
- did not modify the registry entry or weaken the CI tests

## Promotion path (post-demo)

When and if Yaroslav explicitly authorises MODE_B:

1. Re-read this file + `KURAMOTO_RELATION.md` + `INPUT_GAPS.md`.
2. Open MODE_B at Phase 1 (integrity re-check) on a fresh branch.
3. Before any regime-derived feature is built, return to
   `DRO_ARA_DEPENDENCY.md` and set the label to
   `DEPENDS_ON_POST_PATCH_DRO_ARA` + engine SHA.
4. Run the cheap 8-FX cross-asset Kuramoto **floor test** (Track-B
   analogue to the existing equities-only Track A) **before** writing
   any FX-native mechanism brief. If Track-B is MARGINAL/NOT_SUPPORTED,
   the correct action is still `ABORT_LINE` or a tightly-scoped
   DXY-residual exploration, not a revival of combo-family thinking.

## Claim table

| claim | label | evidence |
|---|---|---|
| Demo-critical work is open | SUPPORTED | project memory citations above |
| Cross-asset Kuramoto is more mature than any FX-native line today | PROVEN | Sharpe +1.262 OOS, walk-forward 4/5 passes, live paper day 11/90, PR #136 merged, publication-ready |
| FX-native mechanisms that require rates / options / L2 are blocked by data | PROVEN | `INPUT_GAPS.md` |
| DXY-residual cross-section is the only mechanistically-distinct FX-native corridor with in-repo inputs | PLAUSIBLE | data availability audit; but un-tested, no prior |
| Running 8-FX Kuramoto (Track-B) would clarify whether FX has *any* phase-sync edge | HYPOTHESIS | no such run yet in repo; predicted MARGINAL by Track-A analogue |
| combo_v1 × 8-FX remains falsified and Wave-2-blocked | PROVEN | registry + 12 passing tests + `CANONICAL_FAIL_NOTE.md` |

## Final statement — combo_v1 closure preserved

> combo_v1 is falsified on the 8-FX daily cross-sectional panel under
> locked Wave 1 preregistration. No Wave 2 is authorized. Any
> continuation on FX requires a new FX-native signal family and a new
> preregistration, not parameter rescue.

No MODE_A output weakens this closure. Verifiable at run-time via
`scripts/registry_validator.py --check-pair combo_v1 8fx_daily_close_2100utc`,
which exits non-zero with `BLOCKED`.
