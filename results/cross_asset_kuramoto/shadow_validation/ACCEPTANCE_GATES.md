# Cross-Asset Kuramoto · Acceptance Gates

**Applied by the evaluator at:** every run, with gate-trigger logic at
live-bar counts `{20, 40, 60, 90}`. Bars counted are unique
business-day dates in the live evidence ledger since 2026-04-11.

## Status label vocabulary (closed set)

- `BUILDING_SAMPLE` — fewer than 20 live bars; gates not yet evaluable.
- `WITHIN_EXPECTATION` — live cumulative path inside the p5–p95 historical envelope AND all operational checks pass.
- `UNDERWATCH` — one soft flag is active (cost drag > 1.5× baseline, or forward-fill usage exceeds locked convention, or envelope position in p5–p25 for < 20 consecutive bars).
- `OUTSIDE_EXPECTATION` — live cumulative path below historical p5 envelope for ≥ 20 consecutive evaluated bars.
- `OPERATIONALLY_UNSAFE` — any asset stale > 5 business days OR > 5 % misalignment on a run date OR hash mismatch on a locked artefact.

## Gate decision vocabulary (closed set)

- `CONTINUE_SHADOW` — default decision unless another condition fires.
- `ESCALATE_REVIEW` — driven by §G3, §G4, or any active `UNDERWATCH`/`OUTSIDE_EXPECTATION` state that requires owner review.
- `NO_DEPLOY` — driven by §G3 at 60+ bars with clean ops, or §G2 violation, or §G1 violation.
- `DEPLOYMENT_CANDIDATE_PENDING_OWNER` — reached only at 90 bars, only if every gate family below passes.

## G1 · Operational gates (enforced at every run)

| gate | required |
|---|---|
| silent failures | 0 |
| parameter drift | 0 (hash of `PARAMETER_LOCK.json` must match `LOCK_AUDIT.md`) |
| universe drift | 0 |
| invariant pass rate | 100 % |
| daily run success rate | 100 % |
| unresolved manual reruns | 0 |

**Violation → `NO_DEPLOY`** at any check-in bar count.

## G2 · Cost gates

- Live Sharpe under locked 10 bps cost must remain **> 0** at bar 40+.
- Live Sharpe under 2× cost (20 bps) must remain **> 0** at bar 60+.
- Realized cost drag in bps must not exceed the demo-baseline
  annualized cost drag by > 50 % without flag.

**Violation → `ESCALATE_REVIEW` at 40 bars, `NO_DEPLOY` at 60 bars.**

## G3 · Drift gates

Comparator: `predictive_envelope.csv` (§Phase 4, block-bootstrap of the
demo OOS stream).

| condition | decision |
|---|---|
| Live cumulative return below historical p5 for 20 consecutive evaluated bars | `ESCALATE_REVIEW` |
| Live cumulative return below historical p5 at 60+ bars AND clean ops | `NO_DEPLOY` |
| Live cumulative return below historical p5 at 90 bars (regardless of ops) | `NO_DEPLOY` |
| Live cumulative return above historical p75 at 60+ bars AND clean ops | `DEPLOYMENT_CANDIDATE_PENDING_OWNER` (at 90-bar gate) |

## G4 · Risk gates

- Live max drawdown must not exceed **1.5 × demo-ready OOS max DD**.
  Demo-ready OOS max DD is 16.76 %. Threshold = **25.14 %**.
- If exceeded with clean ops → `ESCALATE_REVIEW`.
- If exceeded with `OPERATIONALLY_UNSAFE` → `NO_DEPLOY`.

## G5 · Truth gate (live bar 90)

At live-bar 90 the evaluator emits exactly one decision:

| inputs all true | decision |
|---|---|
| G1 clean AND G2 clean AND G3 inside p25–p95 AND G4 below 1.5× DD | `DEPLOYMENT_CANDIDATE_PENDING_OWNER` |
| G1 clean AND G2 clean AND G3 within p5–p25 or p95+ AND G4 below 1.5× DD | `CONTINUE_SHADOW` (extend shadow window) |
| any other combination | `NO_DEPLOY` |

Claude Code computes and reports the gate result. Claude Code does
**not** authorize capital deployment.

## Failure contract

Any violation of §R1–R12 (e.g. signal logic change, parameter drift,
suppressed evidence) is an **OPERATIONALLY_UNSAFE** failure and
short-circuits to `NO_DEPLOY`. The evaluator will not attempt to repair
or re-run anything automatically; incidents are appended to
`operational_incidents.csv` and surfaced in `SHADOW_SUMMARY.md`.
