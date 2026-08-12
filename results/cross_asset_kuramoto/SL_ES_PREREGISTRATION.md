# Stuart-Landau ES Proximity · Pre-Registration

**Registered:** 2026-05-06
**Author:** Yaroslav Vasylenko · neuron7xLab
**Module under test:** `core/physics/stuart_landau_es.py` (T2b)
**Reference:** Lee, U. et al. (2025). PNAS 122(44). DOI 10.1073/pnas.2505434122
**Truth gate:** 2026-07-10 (90-bar live shadow gate; co-registered with the
existing Kuramoto-ES rail).

This document is registered **BEFORE** any OOS run, per the project's
falsification ladder discipline (`SEPARATION_FINDING.md`-style
pre-registration: explicit threshold, comparator, p-decision before the
data is touched).

---

## 1. Hypothesis (H1)

Rolling ES proximity from the Stuart-Landau substrate (`rolling_es_proximity`)
peaks **before** R(t) peaks in real cross-asset price data:

> For each crisis episode in the OOS window, the smoothed ES-proximity
> series argmax precedes the smoothed R(t) argmax by τ ≥ 1 bar.

A "crisis episode" = a local maximum in rolling R(t) above the 80th
percentile of its OOS distribution, with prominence ≥ p25.

## 2. Null hypothesis (H0)

ES proximity is independent of R(t) timing — observed leads are the
same as random shuffle.

## 3. Falsification thresholds (registered, frozen)

The hypothesis is **REJECTED** if any of the following holds on the OOS
window:

| Criterion | Threshold | Action on breach |
|---|---|---|
| `leads_rate` (fraction of episodes with τ ≥ 1) | < 0.6 | REJECT H1 |
| `p_value` (permutation test, 999 surrogates) | > 0.05 | REJECT H1 |
| `n_episodes` valid in OOS | < 3 | INSUFFICIENT, do not call |

Multiple comparisons: a single OOS window, two metrics, **AND-decision**
(both must pass to ACCEPT). No alpha adjustment because no metric
selection: both registered up front.

## 4. Data and split

- **Universe:** `BTC, ETH, SPY, GLD, TLT` (5 assets), daily close.
  Source: `~/spikes/cross_asset_sync_regime/data/{btc_usdt,eth_usdt,spy,gld,tlt}_1d.csv`.
  Universe is the same as the live shadow rail; locked.
- **Time range:** intersection of all five (≈ 2017-08-17 → 2026-04-10).
- **Split:** chronological 70/30. Train portion is **not** used for any
  parameter selection — split exists only to guarantee no leakage.
- **Forward fill:** `ffill(limit=1)` (locked convention from `PIPELINE_AUDIT.md#DP5`).
- **No lookahead:** rolling computation is strictly causal (left-to-right).

## 5. Procedure (frozen, exact)

1. Load five price series; align on common business-day index.
2. ffill(limit=1); drop rows still containing NaN.
3. Drop the train portion (first 70 % of bars). Subsequent operations
   touch the OOS portion only.
4. Compute `rolling_es_proximity(prices_oos, window=24, K_steps=12, int_steps=120, seed=20260506, fail_closed=True)`.
   Failure policy (integrity amendment, issue #1358 P1-1 / PR #1425, 2026-07-03):
   this evidence path runs fail-closed — a window whose fit raises aborts the
   replay with its index and cause rather than writing a NaN-backed result. This
   is a failure-POLICY ratchet, NOT a numeric re-registration: it changes no §6
   pre-committed parameter. `fail_closed=True` is metric-NEUTRAL — on this frozen
   OOS window zero windows raise, and the strict rolling-ES series is bit-identical
   to the lenient series under the *current* runtime (proven in
   `artifacts/rolling_es_proximity_oos.strict_replay_proof.json`,
   `metric_equality_basis = strict_vs_lenient_current_runtime`).

   Model-drift disclosure (do not conflate with the flag): the frozen artifact's
   numerics were recorded 2026-05-06 (#536). The Stuart-Landau runtime was then
   updated *after* registration (Hilbert growth-rate μ #1208; fitted-state sweep
   #1362). Under the current runtime, `decision`, `leads_rate`, `n_episodes` and
   `r_peak_indices` reproduce the frozen record exactly, but `p_value` and `taus`
   do not — that shift is caused by the post-registration model update, not by
   `fail_closed`. The pre-registered **REJECT H1** verdict is invariant across
   both models (p_value ≫ 0.05 in each). The committed strict-replay proof
   artifact is the source of truth for these equalities; the flag is a forward
   safety ratchet that surfaces any future masked fit failure rather than silently
   degrading it to a quiet window.
5. Compute rolling Kuramoto R via Hilbert-phase order parameter on the
   same window.
6. Smooth both series with a box-5 mean (consistent with the unit test).
7. Detect R-peaks via `scipy.signal.find_peaks(R_smooth, height=q80, prominence=q25-q5)`
   where qX is the X-th percentile of the OOS smoothed series.
8. For each R-peak at index `t_R`, find `t_ES = argmax(ES_smooth[max(0,t_R-W):t_R+1])`.
9. τ_i = t_R − t_ES.
10. `leads_rate = mean(τ_i ≥ 1)`.
11. Permutation test (999 surrogates): circularly shift `ES_smooth`
    by a random offset uniform in [W, T-W], recompute leads_rate, count
    fraction of surrogate leads_rates ≥ observed.
12. Write all numbers to `artifacts/rolling_es_proximity_oos.json`.

## 6. Pre-committed seeds and parameters

- `window = 24`
- `K_steps = 12`
- `int_steps = 120`
- `seed_engine = 20260506`
- `seed_permutation = 20260506`
- `n_permutations = 999`
- `smooth_width = 5`
- `R_peak_height_quantile = 0.80`
- `R_peak_prominence = q25 − q5 of smoothed R(t) on OOS`

These values are frozen by this document. Any deviation invalidates the
test and requires re-registration (new document, new date, new seed).

## 7. Decision matrix

| `leads_rate` | `p_value` | `n_episodes` | Decision |
|---|---|---|---|
| ≥ 0.60 | ≤ 0.05 | ≥ 3 | **ACCEPT H1** — proceed to T2b shadow integration |
| < 0.60 | any | any | **REJECT H1** — Stuart-Landau substrate does not lead Kuramoto-ES on this window |
| any | > 0.05 | any | **REJECT H1** — observed leads are not distinguishable from random shift |
| any | any | < 3 | **INSUFFICIENT** — do not call; document and revisit on next snapshot |

Decision is computed mechanically by `benchmarks/rolling_es_proximity_oos.py`;
the human role is to honor the decision, not to override it.

## 8. Truth gate alignment

This pre-registration is **decoupled** from the live shadow rail's
2026-07-10 truth gate at the *evidence* level — the OOS test runs on
historical 2017-08-17 → 2026-04-10 data, not live forward bars.

It is **coupled** at the *governance* level: if H1 is ACCEPTED, T2b
becomes a candidate for the same shadow rail, with its own bar-90 gate
to be opened on the next live run.

## 9. Honesty contract

- The OOS bench will write the result regardless of outcome.
- A REJECT result is not a failure of the project; it is a
  registered scientific outcome.
- No retroactive parameter tuning. No alternative metric injection.
- Result published in `artifacts/rolling_es_proximity_oos.json` and
  cited here verbatim once the run completes.

## 10. Result (recorded by the OOS run, 2026-05-06)

```
leads_rate:  0.90625        (29 of 32 episodes had τ ≥ 1)
p_value:     0.7647647...   (999 circular-shift surrogates)
n_episodes:  32
tau_mean:    13.46875       bars
tau_median:  13.5           bars
oos_window:  2023-09-05 → 2026-04-10  (652 bars)
universe:    BTC, ETH, SPY, GLD, TLT
artifact:    artifacts/rolling_es_proximity_oos.json
ran_at_utc:  2026-05-06T07:42:02Z

DECISION:    REJECT H1
```

### Interpretation (no rescue)

The observed `leads_rate = 0.91` looks impressive *in isolation*, but the
permutation test reveals it is **not distinguishable** from a null
distribution where the ES series is circularly shifted by a random
offset (p = 0.76, far above the registered α = 0.05 threshold).

Mechanism: R-peaks tend to cluster in regime-shift episodes; the ES
series has long-range structure such that almost any rolling local
maximum will fall within a 24-bar window before *some* R-peak, yielding
artificially high leads_rates under random shifts. The pre-registered
permutation test catches exactly this window-search artefact.

### Consequences (registered in advance, honored now)

1. **T2b is NOT integrated into the shadow rail.** The Stuart-Landau ES
   proximity stays as research-tier code in `core/physics/stuart_landau_es.py`
   with INV-SL1 / INV-SL2 still enforced (those are universal physics
   bounds independent of the leads claim). INV-T2b is **REJECTED on
   this OOS window** and remains an open hypothesis pending different
   substrate / window / universe.
2. The Disha-facing pitch about "Stuart-Landau leads R(t)" is **withdrawn**.
   The honest claim is now: "Stuart-Landau ES proximity is implemented,
   tested, and pre-registered against Kuramoto-ES — and on 2026-04-10
   cross-asset data it does not show distinguishable predictive lead."
3. No retroactive parameter tuning. No alternative metric injection.
   The next attempt requires a *new* pre-registration document with a
   *new* date, a *new* RNG seed, and a *new* hypothesis (e.g. a different
   peak-detection criterion, a different smoothing kernel, or a
   higher-frequency substrate). Tuning on this window is forbidden.

### What this validates

The pre-registration discipline itself: without §3's permutation test,
this work would have reported leads_rate = 0.91 as a confirmed finding.
With §3, it reports REJECT with a 0.76 p-value. That asymmetry — losing
the easy win in exchange for the truth — is the value of pre-registration.
