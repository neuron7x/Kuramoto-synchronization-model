# Kelly Sizing Theory Boundary

## Scope

This contract covers the local mathematical and implementation boundary for Kelly-related invariants in GeoSync.

## Model

The theoretical small-edge identity is:

    f_star = mu / sigma_squared

This identity belongs to the theory layer. Production sizing may apply caps, scaling, or veto logic. Therefore, adapter output is not required to equal the raw formula unless that adapter explicitly claims raw Kelly behavior.

## Invariants

- INV-KELLY1: raw theoretical fraction equals mu / sigma_squared on analytic fixtures.
- INV-KELLY2: applied fraction never exceeds the configured policy cap.
- INV-KELLY3: expected log growth is maximal at the theoretical fraction on bounded synthetic fixtures.

## Witness rules

Tests must declare seed, sample count, distribution support, grid resolution, and numeric tolerance. Tests must keep the optimum away from grid boundaries. Tests must use bounded fixtures for log-growth checks.

## Claim boundary

These invariants do not prove live alpha, out-of-sample profitability, or market stationarity. Those claims stay retired unless a signed audit artifact supplies data provenance, costs, baselines, confidence intervals, and multiple-testing correction.
