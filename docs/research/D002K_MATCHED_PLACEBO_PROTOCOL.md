# D-002K-P2 — Matched Placebo Window Protocol

**Decision: `D002K_MATCHED_PLACEBO_READY` — `canonical_run_authorized: false`. NOT a D-002J rescue.**

D-002J remains terminally **REFUSED at P7** (`POWER_GATE_REFUSED_UNDERPOWERED`,
axis `effect_too_small`), retained verbatim. D-002K-P2 does **NOT** reopen,
mutate, amend, or rescue D-002J, and authorises no D-002J-P8.

---

## §0 Why matched placebo

A crisis-only evaluation cannot distinguish a substrate that detects
funding-liquidity stress from one that fires on *any* arbitrary window.
The honest control is a **matched placebo**: a NON-crisis window with the
same calendar length, era, baseline-volatility regime, and data
availability as the crisis it shadows.

The single failure mode this phase exists to kill is **cherry-picked
contrast**: choosing placebo windows *after* seeing scores so the
crisis-vs-placebo gap looks large. The defence is structural — the
placebo set is fixed by a deterministic, pre-registered, seed-locked
algorithm **before any scoring opens**. The crisis-vs-placebo contrast
is *predefined*, never hand-selected.

This phase is a registry of date-range specifications plus match
metadata. **Zero data, zero ingestion, zero scoring, zero model run,
zero canonical sweep.**

## §1 Selection algorithm (deterministic, seed-locked)

Algorithm id: `d002k_p2_deterministic_grid_permutation_v1`.
Locked seed: `20260515`. Implementation:
`research/systemic_risk/d002k_placebo_selection.py`.

Inputs are exactly three, all frozen or locked:

1. the FROZEN D-002J P2 crisis-window spec (read-only),
2. the K-P0 `matched_placebo_policy` dict (`n_placebo_per_crisis`,
   `match_on`, `selection`, `locked_before_scoring`),
3. the locked integer seed.

There is **no manual-override parameter**. Steps:

1. Build a fixed pre-registered candidate start-date grid from
   `2014-01-01` (post-2014 secured-rate data regime, the K-P1 anchor)
   to the point-in-time decision frontier `2024-12-31`, step 7 days.
2. For each candidate, form a window with **exactly** the parent
   crisis's trading-day calendar length.
3. Reject any candidate whose buffered span intersects the buffered
   envelope of ANY of the six D-002J registered windows, or whose
   buffered span runs past the point-in-time frontier (§2, §4).
4. Match the five K-P0 covariates (§3 and below).
5. Permute the survivors with `numpy.random.default_rng(seed)` and take
   the first `n_placebo_per_crisis`, sorted by start date.

The five K-P0 `match_on` fields, mapped 1:1:

| K-P0 `match_on` | P2 realisation |
| --- | --- |
| `macro_period` | pre-registered era class; placebo era **must differ** from the parent crisis era |
| `volatility_regime` | pre-registered era baseline-vol bucket (low/medium/high) |
| `calendar_length` | **exact** trading-day equality with the parent crisis |
| `data_availability` | inherits the parent crisis's `data_availability_status` |
| `pre_window_baseline_variance` | proxy baseline-variance statistic within locked relative tolerance `0.25` |

`n_placebo_per_crisis` is read from the K-P0 lock (no hard-coded count;
policy conformance is test-enforced). Same `(crisis, policy, seed)`
yields a **bit-identical** `PlaceboWindow` list.

## §2 Non-overlap discipline

A placebo MUST NOT intersect ANY registered crisis window. The exclusion
zone is each registered window's **buffered** envelope
(`pre_event_buffer .. post_event_buffer`), applied to **all six**
windows CW1..CW6 — not only the three D-002K primaries. The selector
rejects any touching candidate (fail-closed, in code); the test suite
re-scans all six windows independently. Overlap with a registered
crisis window is a hard violation with **no exceptions** and is never
relaxed to pad the placebo count.

## §3 Calendar-length exact match rationale

Pre/post standardized-mean-shift statistics scale with window length: a
longer window mechanically yields a different effect-size distribution.
A placebo of a different length would confound the crisis-vs-placebo
contrast with a pure length artefact. The match is therefore an
**exact** trading-day equality (Mon-Fri business-day count, no holiday
calendar so the count is fully deterministic and data-free), not an
approximate one. Crisis lengths: CW3 = 20, CW4 = 35, CW5 = 16 trading
days.

## §4 Point-in-time consistency

Placebos respect the K-P1 release-boundary rule
(`observation_date <= decision_date`, `release_date <= decision_date`).
The pre-registered decision frontier `2024-12-31` guarantees every
in-window observation is released and final at the locked 2026 D-002K
decision date — the funding-liquidity series publish next-business-day,
so no placebo runs into un-released data. No look-ahead.

## §5 Per-crisis placebo table

Generated deterministically (algo
`d002k_p2_deterministic_grid_permutation_v1`, seed `20260515`):

| Parent crisis | len (td) | Placebo | Window | Era class | Vol bucket |
| --- | --- | --- | --- | --- | --- |
| CW3 | 20 | PLACEBO_01 | 2014-08-13 → 2014-09-09 | post_gfc_zirp_taper | low |
| CW3 | 20 | PLACEBO_02 | 2015-02-04 → 2015-03-03 | post_gfc_zirp_taper | low |
| CW3 | 20 | PLACEBO_03 | 2018-04-18 → 2018-05-15 | gradual_normalization | medium |
| CW3 | 20 | PLACEBO_04 | 2018-10-24 → 2018-11-20 | gradual_normalization | medium |
| CW3 | 20 | PLACEBO_05 | 2021-04-14 → 2021-05-11 | pandemic_policy_era | low |
| CW4 | 35 | PLACEBO_01 | 2014-04-02 → 2014-05-20 | post_gfc_zirp_taper | low |
| CW4 | 35 | PLACEBO_02 | 2017-01-25 → 2017-03-14 | gradual_normalization | low |
| CW4 | 35 | PLACEBO_03 | 2017-11-22 → 2018-01-09 | gradual_normalization | low |
| CW4 | 35 | PLACEBO_04 | 2018-05-16 → 2018-07-03 | gradual_normalization | medium |
| CW4 | 35 | PLACEBO_05 | 2024-04-10 → 2024-05-28 | post_tightening_plateau | medium |
| CW5 | 16 | PLACEBO_01 | 2014-08-13 → 2014-09-03 | post_gfc_zirp_taper | low |
| CW5 | 16 | PLACEBO_02 | 2015-04-22 → 2015-05-13 | post_gfc_zirp_taper | low |
| CW5 | 16 | PLACEBO_03 | 2018-06-06 → 2018-06-27 | gradual_normalization | medium |
| CW5 | 16 | PLACEBO_04 | 2018-08-08 → 2018-08-29 | gradual_normalization | medium |
| CW5 | 16 | PLACEBO_05 | 2024-03-13 → 2024-04-03 | post_tightening_plateau | medium |

15 placebos total; 5 per crisis (K-P0 lock); 0 overlap with any of the
six D-002J registered windows; every calendar length exact-matched.

## §6 Forbidden

- Hand-picked placebo windows (selection is algorithm-only).
- Post-hoc placebo swap after scoring opens.
- Any placebo overlapping ANY registered crisis window (CW1..CW6).
- Relaxing the overlap rule to pad the count → emit
  `D002K_MATCHED_PLACEBO_INCOMPLETE`, report, stop.
- Approximate calendar-length match.
- Any manual-override / hand-picked flag in the registry.
- Promoting this registry into a systemic-risk prediction or a
  bank-level validation claim.

## §7 No-rescue / D-002J frozen reminder

D-002J P2 crisis-window registry is the SOURCE of crisis dates — read,
never edited. D-002J + K-P0 + K-P1 stay byte-exact frozen. D-002K-P2
does not rescue, reopen, or amend D-002J; D-002J stays terminally
REFUSED at P7, retained verbatim. D-002J-P8 must NEVER be dispatched.

Lineage: `D-002G → D-002H REFUSED → D-002I → D-002J P1..P7 #705
POWER_GATE_REFUSED_UNDERPOWERED → D-002K-P0 #706 D002K_PREREG_LOCKED →
D-002K-P1 #707 D002K_SOURCE_OBSERVABLE_CONTRACT_READY → D-002K-P2 this
PR (D002K_MATCHED_PLACEBO_READY)`.

Next legal PR: `feat(x10r,D-002K-P3): high-SNR event metrics` — D-002K-P3
may only open after this D-002K-P2 PR merges.
