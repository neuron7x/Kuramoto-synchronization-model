# PHYSICS_PROOF v3.0 — GeoSync / CoherenceBridge / OTS Capital

> **Non-claim preamble.** The derivations below are **computational-invariant
> derivations**: they prove that the implementation respects the mathematics it
> implements, within stated validity domains. They are **not** proof of market
> physics, **not** a proven predictor, and **not** validated alpha. Nothing here
> asserts profitability, out-of-sample edge, or deployment readiness. For the
> canonical classification and maturity of each result see
> `docs/PHYSICS_CANON.md` and `docs/PHYSICS_MATURITY_MATRIX.md`; for the banned
> framings see `FORBIDDEN_CLAIMS.md`.

## DERIVED / INVARIANT-BOUND (full derivations, invariant-enforced)

### 1. DFA Hurst to gamma (Peng et al. 1994)

**Derivation**: DFA profile `y(k) = sum(x_i - mu)`, detrend in windows of size `s`,
fluctuation `F(s) = sqrt(mean(residual^2))`. Scaling law: `F(s) ~ s^H`.

**PSD connection**: For fractional process with Hurst exponent H,
the power spectral density follows `S(f) ~ f^(-gamma)` where **gamma = 2H + 1**.

| H | gamma | Process |
|---|-------|---------|
| 0.0 | 1.0 | Anti-persistent (mean-reverting) |
| 0.5 | 2.0 | White noise (no memory) |
| 1.0 | 3.0 | Persistent (trending) |

**Invariant**: `abs(gamma - (2*hurst_exponent + 1)) < 1e-10` enforced in
`DFAEstimate.__post_init__`. Compile-time guarantee: gamma is DERIVED, never assigned.

**Cross-validation**: Daubechies db4 wavelet detail coefficient variance scaling
provides independent H estimate. `wavelet_confirmed=True` when `|H_dfa - H_wavelet| < 0.15`.

### 2. Peters SDE Ergodicity Correction (Peters 2019)

**Derivation**: For multiplicative dynamics `dW = mu*dt + sigma*dB` (Ito):

- Ensemble average growth: `g_ens = mu`
- Time average growth: `g_time = mu - sigma^2/2`
- Ergodicity gap: `delta_g = sigma^2/2 >= 0` always

The ensemble and time averages diverge for sigma > 0. Standard expected utility
theory uses ensemble averages, which is invalid for non-ergodic processes.

**Non-Ergodicity Index**: `NEI = sigma^2 / (2*|mu| + eps)`. When NEI >= 0.5, ensemble
statistics are materially misleading.

**Kelly correction**: `f* = max(0, mu/sigma^2) * (1 - min(1, NEI))`

**Pragmatic discount**: `exp(-delta_g * horizon)` provides exponential decay of
edge reliability with holding period.

**Invariant**: `sde_drift_correction = -sigma^2/2` is algebraically exact.

### 3. Forman-Ricci Curvature (INV-RC1..3)

**Proven**: kappa <= 1 for any connected graph (Forman 2003).
kappa in [-1, 1] for build_price_graph output (consecutive integer node IDs).

**Invariant**: See CLAUDE.md INV-RC1..3.

### 4. Kuramoto Order Parameter (INV-K1..7)

**Proven**: R = |1/N * sum(exp(i*theta_k))| in [0, 1] by triangle inequality.
K_c = 2/(pi*g(0)). Finite-size: R ~ O(1/sqrt(N)) incoherent.

### 5. Risk Scalar

**Proven**: `risk_scalar = max(0, 1 - |gamma - 1|)`. Symmetric around
metastable point gamma = 1.0. Lipschitz-1, piecewise linear, in [0, 1].

## EMPIRICALLY CALIBRATED (pending Askar EURUSD tick data)

### Ricci Temporal Offset

`RicciTemporalCalibrator` measures actual kappa to dislocation offset via:
1. Find kappa < threshold events
2. Measure bars until next |return| > 2*sigma
3. Permutation test (n=100, seed=42) for statistical significance

**Status**: NOT calibrated on live data. All `honest_statement` strings
explicitly state this. No ex-ante prediction claims remain in codebase.

**Gate**: `is_predictive=True` requires p < 0.05 AND 30% better than
random permutation AND offset < 80% of max horizon.

### DFA H on Live FX

Validated on synthetic (white noise, persistent, anti-persistent).
Real FX tick validation required before production use.

### NEI Thresholds

NEI < 0.5 ERGODIC, >= 0.5 non-ergodic. From Peters (2019) theory,
not calibrated on FX. Adjust after live backtest.

## KNOWN LIMITATIONS

1. **DFA stationarity assumption**: DFA is more robust than Welch PSD but
   still assumes locally self-similar scaling. Regime transitions within
   the DFA window can bias H estimates.

2. **Ergodicity correction assumes Ito SDE**: Real markets have jumps,
   stochastic volatility, and fat tails. The sigma^2/2 correction is exact for
   geometric Brownian motion but approximate for real FX data.

3. **Ricci curvature is concurrent, not predictive**: Forman-Ricci measures
   current topology. Any temporal offset claim requires empirical calibration
   on the specific instrument and timeframe.

4. **Wavelet cross-validation requires PyWavelets**: If `pywt` is unavailable,
   `wavelet_confirmed=False` (graceful degradation, not failure).

5. **Bootstrap CI removed from DFA**: Latency cost too high for production.
   Use `r_squared` as quality gate instead.

## REFERENCES

- Peng, C.-K. et al. (1994). "Mosaic organization of DNA nucleotides."
  Physical Review E, 49(2), 1685-1689.
- Peters, O. (2019). "The ergodicity problem in economics."
  Nature Physics, 15, 1216-1221.
- Friston, K. (2022). "Active Inference: The Free Energy Principle in Mind,
  Brain, and Behavior." MIT Press.
- Rosenstein, M. T. et al. (1993). "A practical method for calculating largest
  Lyapunov exponents from small data sets." Physica D, 65(1-2), 117-134.
- Forman, R. (2003). "Bochner's method for cell complexes and combinatorial
  Ricci curvature." Discrete and Computational Geometry, 29(3), 323-374.
- Kantelhardt, J.W. et al. (2002). "Multifractal detrended fluctuation analysis."
  Physica A, 316(1-4), 87-114.
