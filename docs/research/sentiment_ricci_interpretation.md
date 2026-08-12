# Sentiment-Ricci Interpretation Guide (Interpretable by Design)

## Intent

This guide explains how to interpret the sentiment-node Ricci pipeline **without over-claiming alpha**.

## Interpretability Layers

### Layer A — Data Layer

- `returns`: log-returns from panel
- `WSB_SENTIMENT`: either Reddit proxy or VIX-inverse proxy
- `sentiment_frozen_z`: train-frozen normalization (first 70%)

Interpretation: this layer ensures comparability and leakage control.

### Layer B — Topology Layer

- Rolling correlation graph (`window=60`)
- Forman-Ricci mean curvature `kappa`

Interpretation: `kappa` is a structural descriptor, not a price prophecy.

### Layer C — Validation Layer

- `IC` (Spearman with next-step target)
- permutation `p_value` (`n=500`, `seed=42`)
- `corr_momentum`, `corr_vol`
- `lead_capture`

Interpretation: all four must align to claim readiness.

## Gate Semantics

A verdict is `SIGNAL_READY` iff:

1. `IC >= 0.08`
2. `p_value < 0.10`
3. `|corr_momentum| < 0.15`
4. `|corr_vol| < 0.15`
5. `lead_capture >= 0.60`

Else verdict is `REJECT`.

## Failure Taxonomy

- **Engine Failure**: no parquet backend (`pyarrow`, `fastparquet`)
- **Data Failure**: missing target column / NaN violations
- **Gate Failure**: orthogonality or three-D thresholds not met

All failures are valid scientific outcomes.

## Anti-Inflation Policy

- No standalone sentiment trading.
- No positive verdict from fallback alone.
- No narrative promotion when gates fail.

## Recommended Reporting Template

```json
{
  "FINAL": "REJECT|SIGNAL_READY",
  "IC": 0.0000,
  "p_value": 0.0000,
  "corr_momentum": 0.0000,
  "corr_vol": 0.0000,
  "lead_capture": 0.0000,
  "error": "optional"
}
```

Use this schema for dashboards and weekly governance review.
