# Pre-Registration Template — Canonical Seven Claim

> Closes audit task 22. Copy this template to
> `research/systemic_risk/preregs/CLAIM_<id>.md` **before** any
> data is touched. Once committed, the file's sha256 is recorded in
> the next `RunManifest.config_hash`. Any post-data edit triggers
> `INVALIDATE` via leakage-sentinel S6 (crisis-date-tuning).

## 1. Claim identifier

`CLAIM_id`: e.g. `CLAIM_2026Q2_MMSR_HARD_PASS`

## 2. Hypothesis (formal)

State the precursor claim in the language of the
`THEORY_PROOFS.md` § 1 inequality (3). Specify:

- Lead-time window `L` (days)
- Critical order-parameter threshold `r_crit ∈ [0, 1]`
- Allowed bootstrap-CI lower bound for AUC

## 3. Data source

| Field | Value |
|---|---|
| Source | e.g. `e-MID daily 2009Q1-2015Q4` |
| Provenance manifest sha256 | `<filled by ingest>` |
| Schema version | `interbank.panel.v1` |
| Sample-size `(n_banks, n_days)` | `(N, T)` |

## 4. Pre-registered config (full snapshot)

Paste the full config dict that drives the pipeline. Every
threshold, window, bootstrap count, RNG seed must appear here.
**Once committed, no field may be retuned without invoking
`INVALIDATE`.**

```json
{
  "lead_time_window_days": 90,
  "r_crit": 0.62,
  "auc_lb_threshold": 0.70,
  "bootstrap_n": 10000,
  "seed": 42,
  "...": "..."
}
```

## 5. Crisis ledger lock

`crisis_lock_timestamp_utc`: ISO-8601 timestamp **before** any
evaluation. Compared against `first_evaluation_timestamp_utc` by
leakage sentinel S6.

## 6. Adversarial roster (frozen)

List the 8 prosecutors against which the candidate must compete.
Default roster is `LADDER_RUNGS`; if expanded for this claim, list
each addition here with its parameter count `k` (for the Occam
penalty).

## 7. Replication plan

| Field | Value |
|---|---|
| Tolerance class | `bit_identical` / `deterministic_with_drift` / `stochastic_seeded` |
| Tolerance numeric | (required iff `stochastic_seeded`) |
| Capsule artefact path | `replication/capsule_<claim_id>.json` |

## 8. Decision rule

`KILL_TRIGGER_LOG_ODDS`: default `-5.0` (cost-ratio `c_FK/c_FP ≈ 1/148`).
If overriding, state explicit Bayes-rule cost matrix and the
posterior threshold.

## 9. Pre-registration commitment

```
sha256(this file) =
sha256(THEORY_PROOFS.md) =
sha256(PROTOCOL.md) =
```

These three sha256s are bound into `RunManifest.config_hash` of the
**next** real-data run. Post-hoc edits → INVALIDATE.

## 10. Authors / reviewers

Pre-registration must be signed by ≥ 2 authors and ≥ 1 reviewer
(external if possible) before `crisis_lock_timestamp_utc`.
