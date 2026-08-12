# Cross-Asset Kuramoto · Shadow Validation Plan

**Status:** binding for this protocol.
**Precondition:** the demo-ready module (`core/cross_asset_kuramoto/`) is
locked at commit `7beea0d`. Nothing below changes signal logic, frozen
parameters, universe, cost model, lag, or forward-fill policy. This
protocol is an **observer**, not a retrainer.

## What this plan does

1. Runs the frozen integrated strategy daily against the locked data
   contract and records append-only evidence under
   `results/cross_asset_kuramoto/shadow_validation/daily/YYYY-MM-DD/`.
2. Compares the forward live cumulative path against a historical
   block-bootstrap envelope drawn from the already-validated integrated
   OOS return stream (`results/cross_asset_kuramoto/demo/equity_curve.csv`).
3. Tracks operational incidents in an append-only ledger.
4. Emits a live scoreboard and a ≤ 500-word human summary on demand.
5. At 20 / 40 / 60 / 90 live-bar milestones, applies `ACCEPTANCE_GATES.md`
   and reports exactly one of `CONTINUE_SHADOW`,
   `DEPLOYMENT_CANDIDATE_PENDING_OWNER`, `ESCALATE_REVIEW`, `NO_DEPLOY`.

## What this plan explicitly does NOT do

- does not retune any parameter
- does not move any threshold
- does not change the 8-asset regime universe or the 5-asset strategy universe
- does not add broker / exchange execution code
- does not optimize anything
- does not fix known caveats (OBS-1 Hilbert non-causality, DP3 snapshot
  staleness, DP5 forward-fill materiality) — those stay documented in
  `INTEGRATION_NOTES.md` and `PIPELINE_AUDIT.md`
- does not overwrite any prior evidence file

## Live-bar source of truth

The spike's paper-trader (`~/spikes/cross_asset_sync_regime/paper_trader.py`)
has been emitting **append-only** daily evidence since **2026-04-11**
into `~/spikes/cross_asset_sync_regime/paper_state/`
(`equity.csv`, `signal_log.jsonl`, `chain.txt`). That ledger is the
primary live-bar source. The shadow validation system reads it
read-only, cross-verifies against a re-run of the frozen integrated
module on the same data, and writes an independent append-only
evidence stream under
`results/cross_asset_kuramoto/shadow_validation/daily/`.

## Responsibilities

| system | writes | reads |
|---|---|---|
| spike paper-trader (already running, daily 22:00 UTC cron) | paper_state/{equity.csv, signal_log.jsonl, chain.txt} | spike data CSVs |
| shadow runner (this protocol) | shadow_validation/daily/YYYY-MM-DD/*, live_scoreboard.csv, operational_incidents.csv, predictive_envelope.csv | spike data CSVs, paper_state/*, demo/equity_curve.csv, frozen module |
| shadow evaluator | live_scoreboard.csv, summaries/* | shadow_validation/daily/*, predictive_envelope.csv |
| shadow report renderer | SHADOW_SUMMARY.md, LIVE_STATE.json | all above |

Two independent evidence streams (paper_trader's + shadow runner's)
create a cross-check: any divergence is surfaced as an operational
incident.

## Gate schedule

Applied at the live-bar counts `{20, 40, 60, 90}` (business days since
`start_date.txt = 2026-04-11`). Every daily run records status labels
and gate decisions in `live_scoreboard.csv`. Final decision at live-bar
90 (≈ 2026-07-10 per spike plan).

## Key non-negotiables

- Evidence is append-only. No overwrites. See §17.S8.
- Seeds are fixed and documented (envelope seed, test seeds).
- Any manual intervention is logged in `operational_incidents.csv`.
- A failed invariant fails the run closed — no silent degradation.
- `combo_v1` closure stays in place. `FX-native` stays deferred.
  Both are verified in the post-execution self-audit.
