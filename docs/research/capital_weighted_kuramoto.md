# Capital-weighted (β) Kuramoto coupling

**Status.** Experimental, opt-in. Default Kuramoto/engine paths do not auto-import this module.

## Implemented files
- `core/kuramoto/capital_weighted.py`
- `tests/unit/core/test_capital_weighted_kuramoto.py`

## Formula

For each oscillator pair (i, j) with baseline coupling `A_ij`,

```
K_ij^β = A_ij · K_0 · (1 + γ · r_ij^{2δ})^{(β−1)/2}
r_i    = depth_mass_i / median(depth_mass)
r_ij   = sqrt(r_i · r_j)
m_i    = mid_price_i · Σ_l (bid_i,l + ask_i,l)         # depth mass
β      = beta_min + (1 − Gini(m)) · (beta_max − beta_min)
```

with β = 1 recovering the baseline (the envelope collapses to `K_0`).

## Inputs
- `baseline_adj`: `(N, N)` non-negative, symmetric, zero-diagonal float64.
- `snapshot`: `L2DepthSnapshot(timestamp_ns, bid_sizes (N, L), ask_sizes (N, L), mid_prices (N,))` or `None`.
- `signal_timestamp_ns`: int decision-time epoch (used for look-ahead validation).
- `cfg`: `CapitalWeightedCouplingConfig` (K0, gamma, delta, beta_min, beta_max, r_floor, normalize, fail_on_future_l2).

## Outputs
`CapitalWeightedCouplingResult(coupling, beta, r, depth_mass, used_fallback, reason, floor_engaged, floor_diagnostic)`.

If `r_floor` is engaged for the median or any per-node ratio,
`result.floor_engaged` is True; coupling remains valid (finite,
symmetric, diag-free) — the flag is informational so the caller can log
or fail-loud as desired. `floor_diagnostic` is a short token describing
which event fired: `"median_clamped"` (median(depth_mass) < r_floor and
the median was clamped up to keep the division finite), `"r_below_floor"`
(at least one r_i is at or below r_floor — typically a zero-depth node),
or `"median_clamped+r_below_floor"` for both. Per-node r_i is **not**
clamped because absolute clamps would break the scale-invariance
``INV-KBETA`` property; only the median is clamped, and only when needed
for finite division. This closes ⊛-audit anti-pattern AP-#5 (silent
fallback) by making the floor event observable to callers.

## Invariants
- `INV-KBETA`: K_ij is finite, non-negative, symmetric, zero-diagonal; β ∈ [beta_min, beta_max]; K is invariant under uniform multiplicative depth scaling.

## Tests
- `test_kbeta_finite_bounded_symmetric_zero_diag`
- `test_beta_one_recovers_baseline_adjacency`
- `test_missing_l2_fallback_is_explicit`
- `test_future_l2_snapshot_rejected`
- `test_depth_mass_non_negative_and_finite`
- `test_scalar_beta_deterministic`
- `test_scale_invariance_under_uniform_depth_scaling`
- `test_no_self_coupling`
- `test_floor_engaged_false_for_healthy_distribution` (⊛-audit AP-#5)
- `test_floor_engaged_true_for_zero_depth_node` (⊛-audit AP-#5)
- plus three validation tests (negative sizes, non-positive mid, ratio floor)

## Known limitations
- The β estimator uses 1 − Gini as a uniformity proxy; alternative concentration measures (Theil index, HHI) are not provided.
- Edgewise ratio uses the geometric mean `r_ij = sqrt(r_i · r_j)`; arithmetic and harmonic alternatives are not benchmarked.
- The ambiguity over depth-mass measurement noise is not modeled; pair with DR-FREE for that.
- No internal handling of cross-venue depth aggregation — caller supplies a single L2 snapshot.

## No-alpha-claim disclaimer
This module is a research primitive that re-shapes the coupling matrix in response to L2 depth concentration. It does not constitute a trading signal nor a claim of out-of-sample edge.

## Source anchor
Kathiravelu (SSRN), adaptive coupling for trading-flow crowding.
