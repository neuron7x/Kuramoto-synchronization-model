# D-002K-P3 — High-SNR Event-Transition Metric Contract

**Decision: `D002K_EVENT_METRICS_READY` — `canonical_run_authorized: false`. NOT a D-002J rescue.**

Lineage: `D-002G → D-002H REFUSED → D-002I → D-002J P1..P7 POWER_GATE_REFUSED_UNDERPOWERED → D-002K-P0 → D-002K-P1 → D-002K-P2 → **D-002K-P3** (this phase)`.

This phase pre-registers the **metric layer only** (executable definitions; **no scoring on data**). It gives the K-P0-locked primary endpoint its full executable mathematical contract and locks the secondary exploratory battery. It sets **no numeric decision threshold** and authorizes **no canonical run**.

---

## §0 — Why high-SNR metrics (the D-002H / D-002I lesson)

D-002H and D-002I diagnosed the *multiplicity-inflation* failure: spreading the confirmatory signal across many endpoints destroys statistical power and inflates the family-wise false-positive rate. D-002K's answer is structural, not statistical loosening:

- **Exactly one** confirmatory endpoint: `pre_post_standardized_mean_shift`, locked in K-P0 and **immutable** here.
- **All** other metrics are `exploratory_only`: they never enter the confirmatory decision, never enter the Bonferroni denominator (`n_windows * n_primary_metrics`, with `n_primary_metrics == 1`), and **cannot** be promoted to primary without a fresh D-002L pre-registration.

Multiplicity is controlled by *scope narrowing* (one high-SNR endpoint), not by relaxing alpha or inflating the effect prior.

## §1 — Primary endpoint: full definition (K-P0 lock, immutable)

`pre_post_standardized_mean_shift` — the single confirmatory endpoint, byte-locked by `artifacts/d002k/prereg/d002k_primary_metric_contract_v1.json::primary_metric_id`. Cohen's-d form:

Given the K-P1 funding-stress observable series, the locked pre-window baseline segment `B`, and the locked in-crisis segment `I`:

1. `mu_pre = mean(B)`
2. `mu_in = mean(I)`
3. `sigma_pre = std(B, ddof=1)` — sample std, degrees of freedom fixed at pre-registration (K-P0 step 4).
4. **metric** `= (mu_in - mu_pre) / sigma_pre` — a single scalar.

- **Pre-window** `B`: the `pre_len` samples ending immediately before crisis `onset_idx` (the locked matched pre-window baseline, per the K-P2 matched-placebo policy calendar).
- **Post-window** `I`: the `post_len` samples starting at `onset_idx` (the locked in-crisis window).
- **Standardization**: z-score vs the pre-window baseline `(mu_pre, sigma_pre)`.

There is **no primary swap**, **no second confirmatory metric**, **no post-hoc primary**. Implementation: `research/systemic_risk/d002k_event_metrics.py:pre_post_standardized_mean_shift`.

## §2 — Secondary exploratory battery (ALL exploratory_only)

The six K-P0-listed secondary metrics. **Each is `confirmatory: false`, `role: secondary_exploratory`.** None may be promoted to primary post-hoc — that is exactly the D-002I multiplicity-inflation failure and is forbidden.

| metric_id | exploratory definition | K-P1 families |
|---|---|---|
| `max_zscore` | peak in-crisis z vs pre-window baseline | level_shift, volatility_burst, transition_steepness |
| `area_under_stress_curve` | composite-trapezoid integral of the in-crisis z-curve | stress_persistence, volatility_burst |
| `recovery_half_life` | samples (post-peak) until z falls to ≤ half its peak; defined no-recovery sentinel `= post_len` | recovery_time, stress_persistence |
| `slope_into_crisis` | OLS slope of the in-crisis z-trajectory | transition_steepness, level_shift |
| `volatility_ratio` | in-crisis sample std / pre-window sample std (ddof=1) | volatility_burst |
| `persistence_above_threshold` | fraction of in-crisis samples with z > a fixed **descriptive** z-level (default 1.0; **not** the decision cut) | stress_persistence, level_shift |

## §3 — Crisis-vs-placebo contrast (uses K-P2 matched placebos)

`crisis_vs_placebo_contrast` computes `Δ = metric(crisis) − mean(metric over K-P2 matched placebos)`. The placebo set is the **predefined, anti-cherry-pick** K-P2 matched-placebo registry — never hand-selected. It returns `{crisis_value, placebo_mean, placebo_std, delta, n_placebos}` — **quantities only**, never a verdict, never a pass/fail.

## §4 — Threshold deferral (power gate owns the cut)

P3 sets **no numeric decision threshold**. Every metric's `decision_threshold_semantics` is `"deferred to D-002K power gate (P-power); NOT set here"`. This contract locks **WHAT** is measured and **HOW**, never the threshold **VALUE**. The numeric cut and the per-window critical value are derived at the later P-power phase from an honestly-sourced effect prior.

## §5 — Determinism + fail-closed

Every metric function is **deterministic** (pure arithmetic on the input slice; identical inputs → bit-identical output). Every metric is **fail-closed** (raises `ValueError`, no silent numeric repair — GeoSync physics discipline) on:

- degenerate baseline (`sigma_pre == 0`),
- insufficient pre/post window length (no truncation, no padding),
- non-finite (`NaN`/`Inf`) input.

A degenerate baseline is an honest error, not a quantity to clamp to epsilon.

## §6 — Forbidden

- Promoting any secondary metric to primary / confirmatory (the D-002I multiplicity-inflation failure).
- Adding a second confirmatory endpoint.
- Setting any numeric decision threshold here (power-gate territory).
- Scoring on real / ingested data — this phase is definitions only; metrics are unit-tested on tiny synthetic arrays for definitional correctness only.
- Authorizing a canonical run.

## §7 — No-rescue / D-002J frozen reminder

D-002K-P3 is part of fresh lineage D-002K and does **NOT** rescue, reopen, amend, or authorize any D-002J-P8. **D-002J remains terminally REFUSED at P7** (`POWER_GATE_REFUSED_UNDERPOWERED`, axis `effect_too_small`); that verdict is retained verbatim. D-002J-P1A + D-002J-P7 stay rejected/refused retained. `canonical_run_authorized_anywhere` stays false.

**Frozen byte-exact:** D-002K-P0 primary-metric contract sha256 `7effc088810ba5933850618312fcad369fdac0386b4a3cab6f14455feeb5a569`; D-002K-P1 observable contract sha256 `952739cbfe4aa16a54eb5684be4bbd653e820eaf92113418e379a3bf8a2a71c3`; D-002K-P2 placebo registry sha256 `435d41df868859f25811236fa4675d01f202682c693d06208922c263ace09413`; D-002K prereg sha256 `2cd923810bf64547cd86ecb403bfd3f12a799cb16c3d10ebc07bc05865fee43f`; D-002J prereg sha256 `f3dc65b7e64b96eafe6f23ca8bdd0e05dc9bf95b12c2658b227bd0340f7975a0`; all `artifacts/d002j/**`, `artifacts/d002k/{prereg,observables,placebo}/**`.

Next legal PR: `feat(x10r,D-002K-P4): power gate before full run` — D-002K-P4 may only open after this D-002K-P3 PR merges. D-002J-P8 must NEVER be dispatched.
