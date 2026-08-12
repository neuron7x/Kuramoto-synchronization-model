# Shadow validation · missing-bar continuity gate

## Problem

The cross-asset Kuramoto shadow validation advances a 90-bar truth gate
(`scripts/evaluate_cross_asset_kuramoto_shadow.py`). Bars are
business-day-clocked; the daily runner fires once at 22:00 UTC
(`ops/systemd/cross_asset_kuramoto_shadow.timer`). Before this change the
evaluator counted live bars as `len(net_ret)` and **never checked that the
bars were consecutive trading days**. A power or network outage during the
22:00 UTC window drops one or more bars from the paper-state ledger; the
evaluator silently continued and could still reach
`DEPLOYMENT_CANDIDATE_PENDING_OWNER` on a discontinuous — therefore
unrepresentative — 90-bar sample. There was no `gap_detected` incident
type; continuity was only enforced upstream in `research/askar/panel_builder.py`
(≤7-day raw-data gap), never in the live evaluation loop.

## Change

Fail-closed continuity gate added to the evaluator:

- `_detect_ledger_gaps(live)` — for each consecutive ledger pair, counts
  missing business days via `np.busday_count`. Weekends never register.
  One missing business day is a probable market holiday (`WARNING`); two
  or more is a continuity breach (`CRITICAL`).
- `_continuity_summary(live)` — aggregates gaps over the full sample:
  `continuity_breach`, `n_gaps`, `n_critical_gaps`, `max_gap_bdays`,
  `total_missing_bdays`.
- `_log_ledger_gaps(live)` — appends a `gap_detected` row per gap to
  `operational_incidents.csv` (runner-identical schema), **idempotently**:
  a gap whose deterministic signature is already logged is never
  re-written, preserving the runner's append-only idempotency contract.
- `_decide_status_and_gate(..., continuity_breach)` — a breach
  short-circuits to `OPERATIONALLY_UNSAFE` / `NO_DEPLOY`, so a
  discontinuous sample can never advance to a deploy candidate regardless
  of how favourable the surviving bars look.
- `LIVE_STATE.json` now publishes the five continuity fields.

## Falsifiable signal

`tests/ops/test_shadow_continuity_gap.py` (10 cases): consecutive days →
no gap; weekend → no gap; single missing business day → `WARNING`; two
missing → `CRITICAL` breach; gate fail-closed on breach (the same state
that yields a deploy candidate when continuous yields `NO_DEPLOY` when
breached); incident logging is idempotent; the evaluator incident schema
matches the runner's `INCIDENT_COLUMNS`.

Run:

```
python -m pytest -q tests/ops/test_shadow_continuity_gap.py
```

The fail-closed direction is the load-bearing assertion: a breach must
override an otherwise-green 90-bar truth gate.
