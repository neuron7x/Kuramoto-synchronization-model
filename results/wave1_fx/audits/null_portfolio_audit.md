# Audit 2 — Null portfolio comparison

Generated UTC: `2026-04-21T21:04:38Z`
Replications per null: **300**, seed=42.
OOS chained window: pos 1148:5852 (= 4704 bars).

## Hypothesis (ROOT_CAUSE §H2)

> combo_v1's 40–45% max DD is structural to the portfolio mechanics, not a tail event specific to the signal.

## Actual combo_v1 (Run B)

- primary median fold-median Sharpe = **-0.0437**
- positive-fold fraction = 0.4369
- max DD (OOS portfolio) = **0.4297**

## Null distributions (quantiles)

### N1_random_scores (n = 300)

**primary Sharpe null:**  `{"p01": -0.7022, "p05": -0.6441, "p25": -0.5353, "p50": -0.4601, "p75": -0.3957, "p95": -0.3114, "p99": -0.2536}`

**max DD null:**          `{"p01": 0.6564, "p05": 0.7413, "p25": 0.8132, "p50": 0.8597, "p75": 0.8941, "p95": 0.9328, "p99": 0.9536}`

**positive-fold frac null:** `{"p01": 0.2027, "p05": 0.2252, "p25": 0.2658, "p50": 0.2973, "p75": 0.3288, "p95": 0.3649, "p99": 0.3919}`

- combo Sharpe percentile in null: **1.0**
- combo DD percentile in null: **0.0**

### N2_sign_shuffled (n = 300)

**primary Sharpe null:**  `{"p01": -0.6458, "p05": -0.5832, "p25": -0.4687, "p50": -0.3932, "p75": -0.3304, "p95": -0.2356, "p99": -0.1502}`

**max DD null:**          `{"p01": 0.5405, "p05": 0.6317, "p25": 0.7537, "p50": 0.8057, "p75": 0.8574, "p95": 0.9112, "p99": 0.9347}`

**positive-fold frac null:** `{"p01": 0.2252, "p05": 0.2523, "p25": 0.2928, "p50": 0.3288, "p75": 0.3559, "p95": 0.3964, "p99": 0.4235}`

- combo Sharpe percentile in null: **1.0**
- combo DD percentile in null: **0.0**

### N3_block_shuffled (n = 300)

**primary Sharpe null:**  `{"p01": -0.275, "p05": -0.2173, "p25": -0.1126, "p50": -0.0543, "p75": -0.0036, "p95": 0.0624, "p99": 0.0934}`

**max DD null:**          `{"p01": 0.1878, "p05": 0.2458, "p25": 0.3344, "p50": 0.431, "p75": 0.521, "p95": 0.6477, "p99": 0.6995}`

**positive-fold frac null:** `{"p01": 0.3423, "p05": 0.3782, "p25": 0.4234, "p50": 0.4505, "p75": 0.482, "p95": 0.5315, "p99": 0.5541}`

- combo Sharpe percentile in null: **0.56**
- combo DD percentile in null: **0.4967**

## Pre-committed label for "DD is structural, not signal-specific"

- SUPPORTED iff combo DD percentile in null N1 ∈ [0.05, 0.95]
- NOT_SUPPORTED iff outside that interval

## Label (pre-committed, N1-based): **NOT_SUPPORTED**

> combo's max DD 0.4297 is a lower-tail event at percentile 0.0 — the
> signal actually reduced DD vs the N1 null mechanics, which contradicts
> H2 in the form it was originally phrased.

## Refined interpretation (explicit, not pre-committed)

Looking at all three nulls in sequence:

| null | what it destroys | combo Sharpe pct | combo DD pct |
|---|---|---:|---:|
| N1 random scores | everything (pure mechanics) | **1.00** | **0.00** |
| N2 sign-shuffled combo | sign alignment only | **1.00** | **0.00** |
| N3 block-shuffled combo (block = 60) | time alignment with returns | **0.56** | **0.50** |

The diagnostic story this tells:

1. combo_v1 has **real cross-sectional structure**. It decisively beats
   N1 and N2 on both Sharpe and DD — it outperforms every one of 300
   random-ranking or sign-shuffled replications.
2. But that structure is **not time-aligned with forward returns**.
   Under N3, which block-shuffles combo (breaking its alignment with
   the return series while preserving its own short-range
   autocorrelation), combo_v1 is statistically indistinguishable from
   its own time-shuffled self (percentiles 0.56 on Sharpe, 0.50 on DD).

Refined conclusion:

> combo_v1's cross-sectional ranking carries information about the
> *contemporaneous* cross-section of FX returns, but it does NOT carry
> time-aligned information about *one-bar-forward* returns. Its DD is
> structural within the family of signals that share combo_v1's own
> cross-sectional autocorrelation profile (N3 median DD ≈ 0.43);
> its DD is NOT structural to "portfolio mechanics with random ranks"
> (N1 median DD ≈ 0.86).

This is the cleaner diagnosis. Both "combo has no edge" and "DD is
structural to the mechanics" as originally stated are too coarse. The
precise statement is: **combo_v1 does not distinguish its own
time-aligned values from block-shuffled versions of itself — so it has
no predictive content about the one-bar-forward FX return at the
resolution of this experiment.**

Implication for ROOT_CAUSE.md:

- H2 (as originally phrased) → RULED_OUT.
- New PROVEN claim: "combo_v1's one-bar-forward predictive content vs
  FX is indistinguishable from block-shuffled self at block = 60 bars
  (N3 Sharpe percentile 0.56, DD percentile 0.50)."
- Additional PROVEN claim: "combo_v1 carries non-trivial contemporaneous
  cross-sectional structure — it beats random-ranking and sign-shuffled
  nulls on both Sharpe and DD at percentile ≥ 0.99."

## Notes on null construction

- **N1 (random scores):** the cleanest null for portfolio mechanics. Shows what DD/Sharpe ranges arise from the top-2 / bottom-2 1-bar-lag rule alone, with zero signal.
- **N2 (sign-shuffled combo):** preserves combo magnitude structure but destroys sign alignment with forward returns.
- **N3 (block-shuffled combo, block=60):** preserves short-range autocorrelation of combo but destroys time-alignment with returns.

## Artefacts

- `null_portfolio_audit.json` — machine-readable summary
- `null_portfolio_samples_N1.csv` — raw N1 sample distributions
