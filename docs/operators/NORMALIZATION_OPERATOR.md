# Normalization Operator

Status: operator specification
Scope: GeoSync inference, Ricci-Kuramoto fusion, validation substrate

## Definition

To normalize is to transform heterogeneous signals into a shared comparison space so that unit scale, sampling density, instrument magnitude, and arbitrary feature amplitude do not dominate structural comparison.

## Canonical form

```text
heterogeneous_signals + normalization_contract -> common_space -> comparable_structure -> normalized_artifact
```

## Operating rule

Normalization is not evidence. It is a precondition for fair comparison between Ricci fields, Kuramoto phase features, liquidity tensors, volatility measures, transaction-cost features, and baseline features.

## Required invariants

1. Each input declares unit, scale, sampling frequency, valid range, and missing-value rule.
2. The transform is declared before downstream use: z-score, robust median/MAD, rank transform, min-max, log transform, volatility scaling, circular normalization, or domain-specific invariant transform.
3. Fit parameters are computed only on the allowed reference window.
4. The artifact records raw hash, transform config, fit parameters, output hash, and time span.
5. The transform must not make non-comparable objects appear comparable.
6. Integrated models must report normalized and raw-scale ablations.
7. If a result survives only under one arbitrary scale choice, the claim is normalization-sensitive.
8. Historical evidence artifacts are not renormalized retroactively.

## GeoSync chain

```text
L2 depth / imbalance / spread / volume -> robust session normalization -> liquidity tensor
Ricci curvature values -> graph-aware normalization -> comparable curvature field
Kuramoto phase / coherence / velocity -> circular-statistical normalization -> phase-state feature space
cost / slippage / turnover -> notional or volatility-adjusted normalization -> cost-aware validation state
Ricci + Kuramoto + liquidity + cost -> common fusion space -> normalized fused fragility kernel
```

## Acceptance gate

A normalized signal is admissible only if it has a declared transform, reference window, provenance record, reproducible command, ablation against raw input, and a demotion rule for scale-sensitive claims.
