# Lyapunov Exponent Theory — Chaos/Order Detection for GeoSync

## Core concept

The Maximal Lyapunov Exponent (MLE) measures the average rate of exponential
divergence of nearby trajectories in phase space:

    λ_max = lim_{t→∞} (1/t) · ln(|δx(t)| / |δx(0)|)

For a scalar time series (e.g. Kuramoto R(t), portfolio returns):
- **λ > 0** → chaotic / unpredictable (nearby trajectories diverge)
- **λ ≈ 0** → marginal / edge-of-chaos (critical transition zone)
- **λ < 0** → stable / predictable (nearby trajectories converge)

## Algorithm: Rosenstein (1993)

1. Delay-embed scalar series: x_i → (x_i, x_{i+τ}, ..., x_{i+(m-1)τ})
2. For each embedded point, find nearest neighbor (excluding temporal vicinity)
3. Track log-divergence of neighbor pairs over time
4. λ_max = slope of mean(ln(divergence)) vs time **on the LINEAR scaling region**

Key parameters:
- **dim** (embedding dimension): 2 for 1D maps, 3-5 for continuous systems
- **tau** (delay): first minimum of mutual information, or 1 for discrete maps
- **max_divergence_steps**: shorter = captures initial exponential growth better

## Scaling-region gate (INV-LE3)

Rosenstein (1993) is only valid where the mean log-divergence curve is
genuinely **linear** — the "most linear region". A noisy or curved window
yields a slope with no dynamical meaning that would otherwise pass silently
(only INV-LE1 finiteness + INV-LE2 sign were enforced before 2026-06-18).

The estimator now computes the coefficient of determination
**R² = 1 − SS_res/SS_tot** of the least-squares fit on the (t, ln d) points in
the fit window. If **R² < R2_MIN (= 0.80)** the curve is not a clean scaling
region and the slope is **not** a trustworthy λ: the function **fails closed**,
returning the module's existing "no reliable estimate" sentinel `0.0` (same
value as the short-series / degenerate-fit paths) and logging a warning.
`diagnostics` (optional out-dict) exposes `r_squared`, `slope`, `n_fit`,
`scaling_ok` for observability. The gate only **demotes** untrustworthy
estimates — it never fabricates a verdict.

**Basis for R2_MIN = 0.80**: the standard "strong linear relationship" floor
for scaling-region fits in the nonlinear-time-series literature. Slightly
looser than the repo's DRO regression floor (R2_MIN = 0.90) because the
Rosenstein curve is an ensemble average over finitely many neighbor pairs and
carries irreducible sampling noise even in clean chaos.

**Known method limitation (documented relaxation, not a bug)**: the Rosenstein
neighbor-divergence estimator measures transient phase-space *stretching* of a
sampled flow, not global contraction. A *damped sinusoid*
x(t)=e^{−0.1t}·sin(t) therefore does NOT present a clean negative-slope
scaling region (its fit has R² ≈ 0.32) — the negative slope the pre-gate code
reported for it was an untrustworthy artifact, now correctly demoted to 0.0.
The honest negative-λ witness is the logistic map in its **stable regime
(r=2.8)**, whose neighbor pairs genuinely contract on a clean linear region
(R² ≈ 1.0, λ ≈ −0.11).

## Calibration results

| System | Theoretical λ | GeoSync MLE | R² | Gate |
|--------|--------------|-------------|-----|------|
| Logistic map r=4 (chaos) | ln(2) = 0.693 | 0.689 | 1.00 | ACCEPT |
| Stable logistic r=2.8 | < 0 | -0.112 | 1.00 | ACCEPT |
| White noise | 0 | 0.000 (demoted) | 0.07 | FLAG non-scaling |
| Damped oscillator | < 0 | 0.000 (demoted) | 0.32 | FLAG non-scaling |
| Kuramoto R(t) subcritical vs supercritical | sub > super | sub > super | — | correct ordering |

## Connection to GeoSync modules

- **R(t) → MLE**: tells you if synchronization dynamics are predictable
- **MLE → Kelly**: λ < 0 → higher conviction → larger fraction
- **MLE → Cryptobiosis**: extreme positive MLE → gradient turbulent → consider DORMANT
- **MLE → GVS**: feeds chaos_health component (|λ| < 0.5 = healthy)

## Invariants

- INV-LE1: MLE finite for any finite bounded input
- INV-LE2: MLE sign matches dynamical regime (noise ≈ 0, stable < 0, chaos > 0)
- INV-LE3: log-divergence linear fit R² ≥ R2_MIN (0.80) OR estimate flagged
  non-scaling and failed closed to 0.0 (never a silent slope)

## References

Rosenstein, Collins & De Luca (1993). Physica D, 65(1-2), 117-134.
Wolf, Swift, Swinney & Vastano (1985). Physica D, 16(3), 285-317.
