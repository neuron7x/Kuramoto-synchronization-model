# D-002J-P4 — Planted Positive Control Protocol v1

Schema anchors: `D002J-POSITIVE-CONTROL-MANIFEST-v1`,
`D002J-POSITIVE-CONTROL-SUMMARY-v1`,
`D002J-POSITIVE-CONTROL-INSTANCE-v1`.

Lineage: `D-002G → D-002H REFUSED → D-002I → D-002J prereg P0 → P1 →
P1A REJECTED → P1B PARTIALLY_VERIFIED → P2 → P2.5 → P3
INGESTION_MANIFEST_READY → P4 (this document) POSITIVE_CONTROLS_READY`.

---

## §0 Why

A pipeline that has never been shown to detect a signal it KNOWS is
present, and to refuse a signal it KNOWS is absent, has no measured
discriminative power. Before any real-data interpretation (P6+), the
pipeline must pass synthetic controls with KNOWN ground truth:

- **Detect when signal exists.** Each positive control plants a signal
  of known onset, effect size, and topology. The pipeline's observable
  must measure that signal above a numeric `pass_threshold`.
- **Reject when signal does not exist.** Each control has a NEGATIVE
  SIBLING: identical synthesis parameters, signal turned off. The
  pipeline's observable on the null sibling MUST fall below
  `pass_threshold`. A null that scores at or above threshold is a
  FALSE POSITIVE and FAILS the control by construction.

P4 PRE-REGISTERS and SYNTHESISES + SCORES these controls. It does NOT
interpret real data, does NOT implement the P5 substrate, does NOT
execute a null (P6), does NOT authorise a canonical run (P8). P5 may
use only P4-validated controls.

All synthesis is deterministic (`numpy.random.default_rng(seed)`), with
no wall-clock dependence and no file reads from any real-data path.

---

## §1 The six control families

Each family is implemented in
`research/systemic_risk/d002j_positive_controls.py` as a
`PositiveControlFamily` subclass exposing
`generate(seed, params) -> ControlInstance` and `score(arr) -> float`.

### PC1 — liquidity shock injection

- **Spec:** `n_nodes` funding-graph nodes; a SUSTAINED elevated
  liquidity-stress shock of magnitude `epsilon` planted on
  `shocked_node` from `t_onset` onward (slow relaxation, not a fast
  transient).
- **Ground truth:** `onset_time`, `effect_size` (= epsilon),
  `propagation_radius`, `shocked_node`.
- **Observable:** worst-node post-onset mean-shift z, SEM-normalised
  (averaging the post window suppresses single-sample extreme noise so
  a transient cannot masquerade as a sustained shock).
- **pass_threshold:** `5.0` — NULL-CALIBRATED. The observable is a
  max over `n_nodes`, an extreme-value statistic whose null
  `E[max] ≈ sqrt(2 ln n_nodes)` (~2.7 for n=24, tail to ~3.5). The
  bar is set ABOVE the empirical null extreme; the planted sustained
  shock drives the signal to ~30. Tightening this bar to fit the null
  is FORBIDDEN — it is deliberately set above it.
- **fail_threshold:** null-sibling worst-node z `≥ 5.0` ⇒
  FALSE_POSITIVE ⇒ REJECT.
- **Forbidden interpretation:** PC1 pass does NOT prove real-world
  liquidity-crisis detection or bank-level validation.

### PC2 — contagion cascade injection

- **Spec:** `n_nodes` with a random row-normalised exposure matrix W;
  default of `defaulted_node` at `t_onset` propagates a DebtRank-style
  cascade through W with `cascade_decay`.
- **Ground truth:** `onset_time`, `cascade_extent`, `cascade_speed`,
  `defaulted_node`.
- **Observable:** fraction of nodes whose post-window MEAN shift
  exceeds 6 pre-window SEM. The MEAN (not a cumulative sum) keeps the
  null bounded — a cumulative sum is a random walk whose variance
  grows with the horizon and would manufacture false positives.
- **pass_threshold:** `0.30` (≥30% of nodes impaired by the cascade).
- **fail_threshold:** null-sibling cascade-extent `≥ 0.30` ⇒
  FALSE_POSITIVE ⇒ REJECT.
- **Forbidden interpretation:** PC2 pass does NOT prove real-world
  contagion detection or DebtRank validation.

### PC3 — balance-sheet impairment injection

- **Spec:** `n_banks` capital-ratio-like series; an asset mark-down of
  magnitude `markdown_mag` planted on a concentrated `impaired_set`
  from `t_onset`.
- **Ground truth:** `onset_time`, `mark_down_magnitude`,
  `impaired_set`.
- **Observable:** worst-decile capital-shift magnitude. A real
  solvency detector reads the LEFT TAIL of the capital distribution,
  not the panel mean, which dilutes a concentrated impaired subset.
- **pass_threshold:** `1.5` (worst-decile leftward shift in
  capital-ratio units).
- **fail_threshold:** null-sibling worst-decile shift `≥ 1.5` ⇒
  FALSE_POSITIVE ⇒ REJECT.
- **Forbidden interpretation:** PC3 pass does NOT prove real-world
  solvency-stress detection or regulatory capital-stress validation.

### PC4 — market-wide volatility regime switch

- **Spec:** univariate returns series; a variance regime switch from
  `sigma_pre` to `sigma_post` at `t_switch`.
- **Ground truth:** `switch_time`, `vol_ratio`, `pre_vol`, `post_vol`.
- **Observable:** post/pre realised-volatility ratio.
- **pass_threshold:** `2.0` (post realised vol ≥ 2× pre).
- **fail_threshold:** null-sibling vol ratio `≥ 2.0` ⇒
  FALSE_POSITIVE ⇒ REJECT.
- **Forbidden interpretation:** PC4 pass does NOT prove real-world
  volatility-regime detection or VIX-based crisis prediction.

### PC5 — information-delay / vintage-leakage trap (INVERTED PASS)

- **Spec:** synthetic vintage series encoded as
  `(observation_date, release_date, value)`. The "signal" array uses
  release dates EARLIER than observation dates by `leakage_delta`
  (it peeks at future-released data — a LOOKAHEAD VIOLATION). The
  null sibling uses release dates AFTER observation dates (point-in-
  time-correct).
- **Ground truth:** `leakage_delta`,
  `expected_failure_mode = LOOKAHEAD_DETECTED`.
- **Observable:** `1.0` iff any `release_date < observation_date`
  (lookahead caught); `0.0` otherwise. This operationalises the P3
  point-in-time contract (`release_date <= decision_date`).
- **pass_threshold:** `1.0`.
- **Forbidden interpretation:** PC5 pass proves the P3 point-in-time
  discipline CATCHES a constructed-leakage detector. It does NOT prove
  real-world leakage absence or live-adapter vintage-correctness.

### PC6 — official-response event shock

- **Spec:** univariate series; a post-intervention variance reduction
  from `sigma_pre` to `sigma_post` at `t_event`.
- **Ground truth:** `intervention_time`, `shift_magnitude`,
  `pre_vol`, `post_vol`.
- **Observable:** pre/post-event realised-vol ratio (>1 ⇒ volatility
  dropped after the intervention).
- **pass_threshold:** `1.5` (pre vol ≥ 1.5× post).
- **fail_threshold:** null-sibling drop ratio `≥ 1.5` ⇒
  FALSE_POSITIVE ⇒ REJECT.
- **Forbidden interpretation:** PC6 pass does NOT prove real-world
  policy-response detection or intervention-effectiveness validation.

---

## §2 Negative sibling discipline

Every control family produces BOTH a `signal_array` and a matched
`null_sibling_array` from the SAME seed-derived RNG. The pipeline
acceptance contract for every non-inverted family is the conjunction:

```
score(signal_array)      >= pass_threshold      (must DETECT)
score(null_sibling_array) <  pass_threshold      (must REJECT)
```

If any negative sibling scores at or above its `pass_threshold`, the
control design is broken and the test FAILS. The threshold is NEVER
loosened to "fit" a leaking null — that would destroy the purpose of
P4. PC1's threshold is intentionally set ABOVE its null extreme; PC2
and PC3's observables were designed to be null-bounded (no random-walk
inflation, left-tail rather than diluted mean).

No control may be promoted without its negative sibling present. The
manifest declares `negative_siblings_required: true`; the summary
asserts `negative_siblings_present == total_control_families`.

---

## §3 PC5 inverted-pass rule

PC5 is the BRIDGE between the P3 point-in-time contract and the P4
pipeline. Its pass criterion is INVERTED: PASS means the pipeline
DETECTS the lookahead violation and would REJECT the leakage-using
detector. `score(signal_array) == 1.0` because the leaking array
contains `release_date < observation_date`; `score(null_sibling_array)
== 0.0` because the point-in-time array never does. If PC5 cannot be
made to flag leakage, the P3 discipline is not executable on the P4
pipeline and that is a reportable fail mode (not a silent pass).

---

## §4 Forbidden claims

Positive controls are SYNTHETIC. PASS on any or all of them:

- does NOT prove real-world performance,
- does NOT prove bank-level validation,
- does NOT prove systemic-risk prediction,
- does NOT rescue D-002H (D-002H REFUSED remains the truthful verdict),
- does NOT authorise any canonical run anywhere.

These boundaries are encoded per-family in
`forbidden_claim_boundary` and aggregated in the DAG verdict's
`forbidden_claims_aggregate` ("positive controls prove real-world
performance" is an explicitly forbidden claim).

---

## §5 Mapping to P5 substrate candidates

Each control informs the admissibility of ≥1 P5 substrate-candidate
mechanism family (the mapping is advisory for P5 design; P4 does not
implement any substrate):

| Control | P5 substrate candidates |
|---|---|
| PC1 | `funding_liquidity_rollover`, `interbank_funding_topology` |
| PC2 | `interbank_exposure_cascade`, `debtrank_propagation` |
| PC3 | `balance_sheet_solvency_proxy`, `capital_ratio_distribution_dynamics` |
| PC4 | `realised_volatility_regime_observer`, `garch_breakpoint_detector` |
| PC5 | `point_in_time_vintage_enforcer`, `lookahead_violation_detector` |
| PC6 | `policy_intervention_breakpoint_detector`, `post_event_regime_shift_observer` |

A P5 substrate candidate is admissible only against the controls it is
mapped to; a substrate that cannot pass its mapped positive control
(or that false-positives on the negative sibling) is inadmissible.

---

## §6 Mapping to P2 crisis window classes

Narrative grounding ONLY — NOT real data. Each control's
`mapped_p2_window_class` ties the synthetic mechanism to a P2 crisis
window class for interpretive context. Producing a synthetic PC1
liquidity shock does NOT mean GeoSync detected the 2019 repo spike;
it means the pipeline can detect a PLANTED liquidity shock whose
narrative analogue is the repo-dysfunction window class.

| Control | P2 window class (narrative only) |
|---|---|
| PC1 | `liquidity_crisis`, `repo_market_dysfunction` |
| PC2 | `contagion_event`, `interbank_default_chain` |
| PC3 | `balance_sheet_impairment`, `afs_htm_unrealized_loss` |
| PC4 | `market_wide_stress`, `vix_spike_regime` |
| PC5 | `vintage_anti_leakage_baseline`, `real_time_information_constraint` |
| PC6 | `official_response`, `policy_intervention` |

---

Next legal PR:
`feat(x10r,D-002J-P5): implement financial-mechanistic substrate
candidates v1`. P5 may open only after this P4 PR merges with decision
`POSITIVE_CONTROLS_READY`, and P5 may use ONLY P4-validated controls.
