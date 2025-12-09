# Mathematical Overview - TradePulse

This document provides a comprehensive map of mathematical artifacts in the TradePulse repository, including formulas, implementations, and their relationships.

## Table of Contents

1. [Core Metrics & Indicators](#core-metrics--indicators)
2. [Backtest Performance Metrics](#backtest-performance-metrics)
3. [Risk Management](#risk-management)
4. [Neuromodulator Mathematics](#neuromodulator-mathematics)
5. [FHMC (Fracto-Hypothalamic Meta-Controller)](#fhmc-fracto-hypothalamic-meta-controller)
6. [Formula-Code Reference Map](#formula-code-reference-map)

---

## Core Metrics & Indicators

### Fractal & Multifractal Analysis

#### 1. Detrended Fluctuation Analysis (DFA)

**Location**: `core/metrics/dfa.py`

**Formula**:
```
For window scale w:
1. Y(k) = Σ[x(i) - x̄] (integrated profile)
2. Fit linear trend in each window segment
3. F²(w) = mean[(Y - trend)²] (fluctuation)
4. α = slope of log(F) vs log(w)
```

**Interpretation**:
- α ≈ 0.5: uncorrelated (white noise)
- α < 0.5: anti-correlated
- α > 0.5: long-range positive correlations
- α ≈ 1.0: 1/f noise (pink noise)
- α > 1.0: non-stationary, unbounded

**Implementation**: `dfa_alpha(x, min_win=50, max_win=2000, n_win=12) -> float`

**Numerical Stability**:
- ✅ Handles empty inputs → returns 0.0
- ✅ Filters non-finite values
- ✅ Uses LOG_SAFE_MIN (1e-15) for log operations
- ✅ Uses VARIANCE_SAFE_MIN (1e-12) for variance checks
- ✅ Validates regression inputs (at least 2 points)

**Tests**: `tests/unit/test_holder.py`, `tests/test_fhmc_minimal.py`

---

#### 2. Hölder Exponent (Wavelet Method)

**Location**: `core/metrics/holder.py`

**Formula**:
```
Using wavelet decomposition:
1. W_j(k) = wavelet coefficients at scale j
2. E_j = mean(|W_j|²) (energy at scale j)
3. log₂(E_j) = const - 2H * log₂(scale_j)
4. H = -slope / 2 (from log-log regression)
```

**Interpretation**:
- H > 1: Very smooth (differentiable)
- H ≈ 0.5: Brownian-like
- H < 0.5: Rough/singular

**Implementation**:
- `holder_exponent_wavelet(x, wavelet="db4", level=None) -> float`
- `local_holder_spectrum(x, window=64) -> (positions, h_values)`
- `singularity_spectrum(x, q_range=(-5, 5)) -> (h, D)`
- `multifractal_width(x) -> float` (returns Δh = h_max - h_min)

**Numerical Stability**:
- ✅ Requires PyWavelets (graceful error if missing)
- ✅ Filters non-finite values
- ✅ Returns default 0.5 for insufficient data (< 32 points)
- ✅ Clamps result to [0, 2] range
- ✅ Uses Q_ZERO_THRESHOLD (0.01) to avoid log(0)
- ✅ Uses COEFF_MIN_THRESHOLD (1e-12) to filter noise

**Tests**: `tests/unit/test_holder.py` (171 lines, comprehensive coverage)

---

#### 3. Aperiodic Spectral Slope

**Location**: `core/metrics/aperiodic.py`

**Formula**:
```
1. PSD = Welch periodogram of signal
2. Select frequencies in [f_lo, f_hi]
3. log₁₀(PSD) = const + m * log₁₀(f)
4. m = slope (1/f^β where β = -m)
```

**Implementation**: `aperiodic_slope(x, fs, f_lo=0.5, f_hi=40.0) -> float`

**Numerical Stability**:
- ✅ Validates fs > 0
- ✅ Returns 0.0 for short series (< 4 points)
- ✅ Uses safe minimums: log₁₀(f + 1e-12), log₁₀(PSD + 1e-24)
- ✅ Requires at least 4 frequency points for regression

---

#### 4. Box-Counting Dimension

**Location**: `core/metrics/fractal_dimension.py`

**Formula**:
```
1. For each box size ε:
   N(ε) = number of boxes containing signal points
2. D = slope of log(N) vs log(1/ε)
```

**Implementation**: `box_counting_dim(signal, eps_list=None) -> float`

**Numerical Stability**:
- ✅ Uses epsilon of 1e-8 in denominator: bins = ceil((max-min)/(eps + 1e-8))
- ✅ Adds 1e-12 before log operations
- ⚠️ **Potential Enhancement**: Could use standardized constants from `core/utils/numeric_constants.py`

---

### Lyapunov-Inspired Metrics

**Location**: `core/metrics/lyapunov.py`

**Formula**:
```
Edge-of-Instability (EOI):
1. Normalize gradient norms: z = (x - μ) / (σ + ε)
2. EOI = autocorr(z[:-1], z[1:])
```

**Implementation**: `eoi_edge_of_instability(grad_norm_series, win=200) -> float`

**Numerical Stability**:
- ✅ Uses eps=1e-8 for division safety
- ✅ Handles empty windows → returns 0.0
- ⚠️ **Potential Enhancement**: Could validate autocorr result is finite

---

## Backtest Performance Metrics

**Location**: `backtest/performance.py`

### Sharpe Ratio

**Formula**:
```
SR = (μ_excess / σ_excess) * √(periods_per_year)

where:
- μ_excess = mean(returns - rf_rate)
- σ_excess = std(excess_returns)
```

**Implementation**: Lines 112-129 in `compute_performance_metrics()`

**Numerical Stability**:
- ✅ Checks volatility > 0 before division
- ✅ Uses ddof=1 for sample standard deviation
- ✅ Handles returns.size > 1 correctly

---

### Probabilistic Sharpe Ratio (PSR)

**Formula**:
```
PSR = Φ(z)

where z = (SR - SR_target) * √(n-1) / √(1 - γ*SR + ((κ-1)/4)*SR²)

and:
- γ = skewness
- κ = excess kurtosis
- Φ = standard normal CDF
```

**Implementation**: Lines 131-149 in `compute_performance_metrics()`

**Numerical Stability**:
- ✅ Checks m2 > 1e-12 before computing higher moments
- ✅ Checks denominator > 1e-12 before computing z-score
- ✅ Handles division by zero in skewness/kurtosis calculation

**Reference**: Bailey, D. H., & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier"

---

### Sortino Ratio

**Formula**:
```
Sortino = (μ_excess / σ_downside) * √(periods_per_year)

where σ_downside = std(returns[returns < 0])
```

**Implementation**: Lines 151-166

**Numerical Stability**:
- ✅ Only computes if downside.size > 0
- ✅ Uses ddof=1 for sample std when size > 1
- ✅ Returns math.inf if no downside (all returns positive)

---

### Certainty Equivalent Return

**Formula**:
```
CE = (1 + μ - 0.5*λ*σ²)^periods_per_year - 1

where:
- μ = mean return per period
- σ² = variance per period
- λ = risk aversion coefficient
```

**Implementation**: Lines 168-191

**Numerical Stability**:
- ✅ Checks base > 0 before taking log
- ✅ Checks for overflow: exponent < log(float_max)
- ✅ Checks for underflow: exponent > log(float_tiny)
- ✅ Returns -1.0 for non-positive base or extreme underflow
- ✅ Returns math.inf for extreme overflow

---

### CAGR (Compound Annual Growth Rate)

**Formula**:
```
CAGR = (final_value / initial_value)^(1/years) - 1
```

**Implementation**: Lines 193-202

**Numerical Stability**:
- ✅ Validates initial_capital > 0
- ✅ Validates final_equity > 0
- ✅ Validates years > 0

---

### Expected Shortfall (ES / CVaR)

**Formula**:
```
ES_α = mean(returns | returns ≤ VaR_α)

where VaR_α = α-quantile of returns
```

**Implementation**: Lines 209-215

**Numerical Stability**:
- ✅ Clips alpha to [1e-4, 0.5] to avoid extreme quantiles
- ✅ Handles empty tail_losses (returns ES only if tail exists)

---

### Alpha & Beta (CAPM)

**Formula**:
```
β = Cov(R_p - R_f, R_b - R_f) / Var(R_b - R_f)
α = (μ_p - R_f) - β * (μ_b - R_f)
```

**Implementation**: Lines 228-259

**Numerical Stability**:
- ✅ Aligns portfolio and benchmark returns (takes min length)
- ✅ Filters non-finite values with mask
- ✅ Checks benchmark_var > 1e-12 before computing beta
- ✅ Uses ddof=1 for covariance when size > 1

---

### Information Ratio & Tracking Error

**Formula**:
```
TE = std(R_p - R_b)  (tracking error)
IR = mean(R_p - R_b) / TE * √(periods_per_year)
```

**Implementation**: Lines 260-270

**Numerical Stability**:
- ✅ Checks tracking_error > 1e-12 before division
- ✅ Uses ddof=1 for sample standard deviation

---

## Risk Management

**Location**: `src/tradepulse/risk/risk_core.py`

### Value at Risk (VaR) & Expected Shortfall (ES)

**Formula**:
```
Let L = -returns (losses)

VaR_α = quantile(L, α)
ES_α = mean(L | L ≥ VaR_α)
```

**Implementation**: `var_es(returns, alpha=0.975) -> (VaR, ES)`

**Numerical Stability**:
- ✅ Returns (0.0, 0.0) for empty inputs
- ✅ Fallback: ES = VaR if tail_losses is empty
- ⚠️ **Note**: Positive values indicate losses (sign convention)

**Documentation**:
```python
"""
Compute Value at Risk and Expected Shortfall.

.. math::

    \text{VaR}_\alpha = Q_\alpha(-r)
    \text{ES}_\alpha = \mathbb{E}[-r \mid -r \geq \text{VaR}_\alpha]

Assumptions:
- alpha ∈ (0, 1), typically 0.95 or 0.975
- returns can be any real values
- Positive VaR/ES indicate losses
"""
```

---

### Kelly Criterion with Regime Shrinkage

**Formula**:
```
f_raw = μ / σ²
f = λ * min(f_max, max(0, f_raw))

where λ = {
  0.0  for KILL
  0.5  for CAUTION  
  1.0  for EMERGENT
}
```

**Implementation**: `kelly_shrink(mu, sigma2, ews_level, f_max=1.0) -> float`

**Numerical Stability**:
- ✅ Returns 0.0 if sigma2 ≤ 0
- ✅ Clamps f_raw to [0, f_max]
- ✅ Applies regime-based shrinkage

**Documentation**:
```python
"""
Compute Kelly fraction with regime-aware shrinkage.

.. math::

    f_{\text{raw}} = \frac{\mu}{\sigma^2}
    f = \lambda \cdot \min(f_{\max}, \max(0, f_{\text{raw}}))

Regime scaling: λ = {0 for KILL, 0.5 for CAUTION, 1 for EMERGENT}
"""
```

---

### Position Sizing

**Formula**:
```
size = size_hint * kelly_fraction
size_final = clip(size, 0, f_max)
```

**Implementation**: `compute_final_size(size_hint, kelly_fraction, f_max=1.0) -> float`

---

## Neuromodulator Mathematics

### Neuro-Optimizer Homeostatic Balance

**Location**: `src/tradepulse/core/neuro/neuro_optimizer.py`

**Homeostatic Setpoints** (Lines 139-150):
```python
dopamine_serotonin_target_ratio = 1.67
gaba_excitation_target_balance = 1.5
arousal_attention_coherence_target = 0.75
```

**Multi-Objective Function**:
```
J = w_perf * J_performance + w_balance * J_balance + w_stability * J_stability

where:
- w_perf = 0.45 (default)
- w_balance = 0.35 (default)
- w_stability = 0.20 (default)
- Σw_i = 1.0 (validated in __post_init__)
```

**Gradient Update with Momentum**:
```
v_t = momentum * v_{t-1} + learning_rate * ∇J
θ_t = θ_{t-1} - v_t
```

**Numerical Stability**:
- ✅ Validates weights sum to 1.0
- ✅ Validates learning_rate ∈ (0, 1)
- ✅ Validates momentum ∈ [0, 1)

---

### Kuramoto Synchrony

**Location**: `src/tradepulse/features/kuramoto.py`

**Order Parameter**:
```
R = |⟨e^{iθ_j}⟩| = |(1/N) Σ_j e^{iθ_j}|

where θ_j are phases of oscillators
```

**Interpretation**:
- R ≈ 0: Chaotic (no synchrony)
- R ≈ 1: Emergent (high synchrony)

**Thresholds** (Lines 52-55):
- R > 0.7: EMERGENT phase
- R < 0.4: CHAOTIC phase
- 0.4 ≤ R ≤ 0.7: TRANSITIONAL

**Implementation**: `KuramotoSynchrony.fit_transform(prices) -> dict`

---

## FHMC (Fracto-Hypothalamic Meta-Controller)

**Location**: `runtime/thermo_controller.py` (FHMC class, lines 1327-1451)

**Specification**: `docs/spec_fhmc.md`

### Flip-Flop (Hysteresis State Machine)

**Formula** (from spec):
```
State_{t+1} = {
  SLEEP,   if TH(t) > θ_hi  ∨  OX(t) < ω_lo
  WAKE,    if TH(t) < θ_lo  ∧  OX(t) > ω_hi
  State_t, otherwise
}
```

**Implementation** (lines 1414-1425):
```python
def flipflop_step(self) -> str:
    theta_lo = self.cfg["flipflop"].get("theta_lo", 0.6)
    theta_hi = self.cfg["flipflop"].get("theta_hi", 0.8)
    omega_lo = self.cfg["flipflop"].get("omega_lo", 0.4)
    omega_hi = self.cfg["flipflop"].get("omega_hi", 0.6)
    
    if self.state == "WAKE":
        if self._th > theta_hi or self._ox < omega_lo:
            self.state = "SLEEP"
    else:  # SLEEP
        if self._th < theta_lo and self._ox > omega_hi:
            self.state = "WAKE"
    return self.state
```

**Validation**: ✅ **CORRECT** - Implementation matches specification exactly

---

### Orexin-Arousal

**Formula** (from spec):
```
OX(t) = σ(k₁·E[r|π_t] + k₂·novelty(t) + k₃·load(t))

where σ(x) = 1/(1 + e^{-x}) (sigmoid)
```

**Implementation** (lines 1394-1402):
```python
def compute_orexin(self, exp_return: float, novelty: float, load: float) -> float:
    orexin_cfg = self.cfg["orexin"]
    stimulus = (
        orexin_cfg.get("k1", 1.0) * exp_return
        + orexin_cfg.get("k2", 0.7) * novelty
        + orexin_cfg.get("k3", 0.3) * load
    )
    self._ox = float(1.0 / (1.0 + np.exp(-stimulus)))
    return self._ox
```

**Validation**: ✅ **CORRECT** - Implementation matches specification

**Numerical Stability**:
- ✅ Uses numpy's exp (handles overflow gracefully)
- ⚠️ **Potential Enhancement**: Could use stable sigmoid for extreme stimuli

---

### Threat-Imminence

**Formula** (from spec):
```
TH(t) = w₁·z(MaxDD) + w₂·z(VolShock) + w₃·CPScore(t)

then apply tanh for bounding
```

**Implementation** (lines 1404-1412):
```python
def compute_threat(self, maxdd: float, volshock: float, cp_score: float) -> float:
    threat_cfg = self.cfg["threat"]
    weighted = (
        threat_cfg.get("w_dd", 0.5) * max(0.0, maxdd)
        + threat_cfg.get("w_vol", 0.3) * max(0.0, volshock)
        + threat_cfg.get("w_cp", 0.2) * max(0.0, cp_score)
    )
    self._th = float(np.tanh(weighted))
    return self._th
```

**Validation**: ✅ **CORRECT** - Implementation matches specification

**Numerical Stability**:
- ✅ Uses max(0.0, x) to clip negative inputs
- ✅ tanh provides natural bounding to [-1, 1]

---

## Formula-Code Reference Map

| Formula/Metric | Specification | Implementation | Test Coverage |
|----------------|---------------|----------------|---------------|
| DFA α-exponent | docs/spec_fhmc.md:40 | core/metrics/dfa.py:27 | tests/test_fhmc_minimal.py:8 |
| Aperiodic 1/f slope | docs/spec_fhmc.md:43 | core/metrics/aperiodic.py:11 | tests/neuro/advanced/* |
| Hölder exponent | docs/spec_fhmc.md:83 | core/metrics/holder.py:46 | tests/unit/test_holder.py |
| FHMC Flip-flop | docs/spec_fhmc.md:7 | runtime/thermo_controller.py:1414 | tests/test_fhmc_minimal.py:14 |
| Orexin-arousal | docs/spec_fhmc.md:18 | runtime/thermo_controller.py:1394 | tests/test_fhmc_minimal.py:18 |
| Threat-imminence | docs/spec_fhmc.md:25 | runtime/thermo_controller.py:1404 | tests/test_fhmc_minimal.py:18 |
| Sharpe Ratio | - | backtest/performance.py:112 | tests/unit/backtest/test_performance_metrics.py |
| Probabilistic Sharpe | Bailey & López de Prado (2012) | backtest/performance.py:131 | tests/unit/backtest/test_performance_metrics.py |
| Sortino Ratio | - | backtest/performance.py:151 | tests/unit/backtest/test_performance_metrics.py |
| CAGR | - | backtest/performance.py:193 | tests/unit/backtest/test_performance_metrics.py |
| VaR/ES | - | src/tradepulse/risk/risk_core.py:41 | tests/apps/test_risk_guardian.py |
| Kelly Criterion | - | src/tradepulse/risk/risk_core.py:79 | tests/sandbox/test_risk_engine.py |
| Kuramoto Order | - | src/tradepulse/features/kuramoto.py:70 | tests/neuro/advanced/* |

---

## Numerical Constants Reference

**Location**: `core/utils/numeric_constants.py`

Standard constants used throughout the codebase:

| Constant | Value | Purpose |
|----------|-------|---------|
| `DIV_SAFE_MIN` | 1e-12 | Division by zero protection |
| `LOG_SAFE_MIN` | 1e-15 | Logarithm argument minimum |
| `VARIANCE_SAFE_MIN` | 1e-12 | Variance/std threshold |
| `PROB_CLIP_MIN` | 1e-10 | Probability lower bound |
| `PROB_CLIP_MAX` | 1 - 1e-10 | Probability upper bound |
| `ZERO_TOL` | 1e-12 | Zero comparison tolerance |

**Helper Functions**:
- `safe_divide(num, denom, default=0.0)` - Division with fallback
- `safe_log(value)` - Log with clamping
- `safe_sqrt(value)` - Sqrt with non-negative enforcement
- `clip_probability(prob)` - Probability validation
- `is_effectively_zero(value)` - Zero check with tolerance

---

## Documentation Standards

All mathematical functions should include:

1. **Docstring with LaTeX formula**:
   ```python
   """
   Compute metric X.
   
   .. math::
   
       X = \frac{\sum_i w_i r_i}{\sum_i w_i}
   
   Parameters
   ----------
   r_i : array-like
       Returns, expected in [-1, 1]
   w_i : array-like
       Weights, must be non-negative
   
   Returns
   -------
   float
       Weighted average return
   
   Notes
   -----
   Assumes at least one non-zero weight.
   """
   ```

2. **Input range documentation**
3. **Edge case behavior**
4. **Numerical stability notes**
5. **References to papers/specs**

---

## Testing Standards

Each mathematical function should have tests covering:

1. **Invariants**: monotonicity, symmetry, scale-invariance
2. **Boundary cases**: zero vectors, extreme values, single-element
3. **Reference checks**: comparison with known results or alternative implementations
4. **Numerical stability**: near-zero denominators, overflow/underflow

**Target Coverage**: ≥90% for critical mathematical paths

---

## Related Documentation

- [FHMC Specification](spec_fhmc.md) - Complete formal equations
- [Neuro-Optimization Guide](neuro_optimization_guide.md) - Neuromodulator optimization
- [Architecture](ARCHITECTURE.md) - System design overview

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-09  
**Maintainer**: TradePulse Engineering Team
