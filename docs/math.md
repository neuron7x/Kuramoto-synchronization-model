# Mathematical Foundations of TradePulse

This document provides a comprehensive mathematical overview of the core algorithms
and indicators implemented in TradePulse. All formulas follow rigorous mathematical
notation and include complexity analysis, numerical stability considerations, and
theoretical foundations.

---

## Table of Contents

1. [Phase Synchronization & Kuramoto Model](#phase-synchronization--kuramoto-model)
2. [Geometric Curvature & Ricci Flow](#geometric-curvature--ricci-flow)
3. [Information Theory & Entropy](#information-theory--entropy)
4. [Fractal Analysis & Self-Similarity](#fractal-analysis--self-similarity)
5. [Long-Range Correlations & DFA](#long-range-correlations--dfa)
6. [Stochastic Processes](#stochastic-processes)
7. [Numerical Stability & Precision](#numerical-stability--precision)

---

## Phase Synchronization & Kuramoto Model

### Analytic Signal & Hilbert Transform

The instantaneous phase θ(t) of a real signal x(t) is extracted via the analytic signal:

```
z(t) = x(t) + i·ℋ{x}(t)
θ(t) = arg[z(t)] = arctan2(ℋ{x}(t), x(t)) ∈ [-π, π]
```

where ℋ{·} is the Hilbert transform:

```
ℋ{x}(t) = (1/π) P.V. ∫₋∞^∞ [x(τ)/(t-τ)] dτ
```

**Implementation:** Via FFT in frequency domain:
```
ℋ{x}(t) = IFFT{-i·sgn(f)·FFT{x}(t)}
```

**References:**
- Gabor, D. (1946). Theory of communication. Journal of the IEE, 93(26).
- Boashash, B. (1992). Estimating the instantaneous frequency of a signal. IEEE, 80(4).

### Kuramoto Order Parameter

For N coupled oscillators with phases θⱼ ∈ [-π, π], the order parameter quantifies synchronization:

```
R = |Z| / N,  where Z = ∑ⱼ₌₁ᴺ exp(iθⱼ)
```

Equivalently:
```
R = √[(∑ⱼ cos(θⱼ))² + (∑ⱼ sin(θⱼ))²] / N ∈ [0, 1]
```

**Interpretation:**
- R = 1: Perfect synchronization (all phases aligned)
- R = 0: Complete desynchronization (uniform phase distribution)

**Weighted variant:**
```
R = |∑ⱼ wⱼ·exp(iθⱼ)| / ∑ⱼ wⱼ
```

**Complexity:** O(N) per timestep

**References:**
- Kuramoto, Y. (1975). Self-entrainment of coupled non-linear oscillators. Lecture Notes in Physics, 39.
- Acebrón, J. A., et al. (2005). The Kuramoto model. Reviews of Modern Physics, 77(1), 137.

---

## Geometric Curvature & Ricci Flow

### Ollivier-Ricci Curvature

For a graph G = (V, E) with probability distributions μₓ and μᵧ on nodes x, y ∈ V,
the Ollivier-Ricci curvature of edge (x, y) is:

```
κ(x, y) = 1 - W₁(μₓ, μᵧ) / d(x, y)
```

where:
- W₁(μₓ, μᵧ) is the 1-Wasserstein (Earth Mover's) distance
- d(x, y) is the geodesic distance between x and y

### Wasserstein-1 Distance

For discrete probability distributions on support {x₁, ..., xₙ} with CDFs Fμ and Fν:

```
W₁(μ, ν) = ∫₋∞^∞ |Fμ(x) - Fν(x)| dx
```

Discrete form:
```
W₁ = ∑ᵢ₌₁ⁿ⁻¹ |Fμ(xᵢ) - Fν(xᵢ)| · (xᵢ₊₁ - xᵢ)
```

**Curvature Interpretation:**
- κ > 0: Positive curvature (clustering, spherical geometry)
- κ = 0: Flat (Euclidean)
- κ < 0: Negative curvature (dispersion, hyperbolic geometry)

**Complexity:** O(n log n) for sorting, O(n) for distance computation

**References:**
- Ollivier, Y. (2009). Ricci curvature of Markov chains. Journal of Functional Analysis, 256(3).
- Villani, C. (2009). Optimal Transport: Old and New. Springer.

---

## Information Theory & Entropy

### Shannon Entropy

For discrete probability distribution P = {p₁, ..., pₙ}:

```
H(P) = -∑ᵢ₌₁ⁿ pᵢ · log(pᵢ)  [nats, natural log]
```

**Properties:**
- H ≥ 0 (non-negative)
- H = 0 ⟺ P is deterministic (one pᵢ = 1)
- H ≤ log(n) with equality for uniform distribution
- H is concave in P

**Delta Entropy (Temporal Derivative):**
```
ΔH(t) = H(t₂) - H(t₁)
```

where t₁ and t₂ are consecutive time windows.

**Interpretation:**
- ΔH > 0: Increasing uncertainty (regime transition)
- ΔH < 0: Decreasing uncertainty (consolidation)

**Complexity:** O(N + B) where N = sample size, B = number of bins

**References:**
- Shannon, C. E. (1948). A mathematical theory of communication. Bell System Technical Journal, 27(3).
- Cover, T. M., & Thomas, J. A. (2006). Elements of Information Theory. Wiley.

---

## Fractal Analysis & Self-Similarity

### Box-Counting Dimension

For a fractal set, the box-counting dimension D is:

```
D = lim_{ε→0} [log N(ε) / log(1/ε)]
```

where N(ε) is the number of boxes of size ε needed to cover the set.

**Practical estimation:** Linear regression on log-log plot:
```
log N(ε) ~ -D · log ε + const
```

**Interpretation:**
- D = 1.0: Smooth curve (Euclidean)
- D ≈ 1.5: Brownian motion (typical for financial data)
- D → 2.0: Space-filling, highly irregular

**Complexity:** O(M·N) where M = number of scales, N = signal length

**References:**
- Mandelbrot, B. B. (1982). The Fractal Geometry of Nature. W.H. Freeman.
- Higuchi, T. (1988). Approach to an irregular time series. Physica D, 31(2).

---

## Long-Range Correlations & DFA

### Detrended Fluctuation Analysis

DFA quantifies long-range correlations via scaling exponent α:

**Algorithm:**
1. Integrate signal: y(t) = ∑ᵢ₌₁ᵗ [x(i) - x̄]
2. Divide into segments of size s
3. Detrend each segment via polynomial fit
4. Compute RMS fluctuation: F(s) = √[⟨(y - yₜᵣₑₙ)²⟩]
5. Analyze scaling: F(s) ~ s^α

**Scaling Exponent Interpretation:**
- α = 0.5: White noise (uncorrelated)
- α < 0.5: Anti-correlated (mean-reverting)
- α > 0.5: Long-range correlations (persistent trends)
- α ≈ 1.0: 1/f noise (pink noise, scale-invariant)
- α ≈ 1.5: Brownian motion

**Complexity:** O(N·W) where N = signal length, W = number of windows

**References:**
- Peng, C. K., et al. (1994). Mosaic organization of DNA nucleotides. Physical Review E, 49(2).
- Kantelhardt, J. W., et al. (2002). Multifractal DFA. Physica A, 316(1-4).

---

## Stochastic Processes

Key formulas mirror the specification in `docs/spec_fhmc.md`:

### Ornstein-Uhlenbeck Process
```
dx = -θ(x - μ) dt + σ dW
```

where:
- θ: mean reversion rate
- μ: long-term mean
- σ: volatility
- W: Wiener process

### Flip-flop hysteresis transitions
State transitions with hysteresis thresholds for regime switching.

### Orexin/arousal logistic modulation
```
orexin(t) = 1 / (1 + exp(-k·(stress(t) - threshold)))
```

### Threat imminence blending weighted risk metrics
Combines multiple risk signals with distance-dependent weighting.

### Reward/policy error (RPE/APE) updates
Temporal difference learning:
```
δ(t) = r(t) + γ·V(s_{t+1}) - V(s_t)
```

### Fractional Lévy diffusion parameter perturbations
Heavy-tailed distributions for modeling extreme events.

---

## Numerical Stability & Precision

### Floating-Point Considerations

**Machine Epsilon:**
- float32: ε ≈ 1.19×10⁻⁷
- float64: ε ≈ 2.22×10⁻¹⁶

**Denormal Numbers:**
- Threshold: 10⁻⁸ for clipping small values to zero
- Prevents performance degradation from subnormal arithmetic

**Loss of Significance:**
- Catastrophic cancellation in subtraction of nearly equal values
- Mitigated via Kahan summation or pairwise summation

### Numerical Safeguards

1. **NaN/Inf Filtering:** All non-finite values removed before computation
2. **Normalization:** Signals scaled to [-1, 1] to prevent overflow/underflow
3. **Logarithm Safety:** log(x + ε) with ε = 10⁻¹² to prevent log(0)
4. **Division Safety:** Check denominator > threshold before division
5. **Mixed Precision:** Intermediate calculations in float64 even with float32 input

### Complexity Analysis

All algorithms document:
- **Time Complexity:** Big-O notation for worst-case runtime
- **Space Complexity:** Auxiliary memory requirements
- **Cache Efficiency:** Memory access patterns for CPU/GPU optimization

---

## References

### Core Mathematical Texts
1. Kuramoto, Y. (1984). Chemical Oscillations, Waves, and Turbulence. Springer.
2. Villani, C. (2009). Optimal Transport: Old and New. Springer.
3. Cover, T. M., & Thomas, J. A. (2006). Elements of Information Theory. Wiley.
4. Mandelbrot, B. B. (1982). The Fractal Geometry of Nature. W.H. Freeman.

### Academic Papers
1. Acebrón, J. A., et al. (2005). The Kuramoto model. Reviews of Modern Physics, 77(1).
2. Ollivier, Y. (2009). Ricci curvature of Markov chains. J. Functional Analysis, 256(3).
3. Peng, C. K., et al. (1994). Mosaic organization of DNA. Physical Review E, 49(2).
4. Shannon, C. E. (1948). A mathematical theory of communication. Bell System Tech. J., 27(3).

### Numerical Analysis
1. Higham, N. J. (2002). Accuracy and Stability of Numerical Algorithms. SIAM.
2. Golub, G. H., & Van Loan, C. F. (2013). Matrix Computations. JHU Press.

---

## Implementation Notes

All mathematical implementations in TradePulse:
- ✓ Use IEEE 754 floating-point arithmetic
- ✓ Document numerical stability guarantees
- ✓ Include complexity analysis (time and space)
- ✓ Provide academic references
- ✓ Implement defensive programming (NaN/Inf handling)
- ✓ Support both CPU and GPU execution where applicable
- ✓ Include unit tests with known mathematical properties
- ✓ Expose metrics for observability

For detailed implementation, see:
- **Kuramoto:** `core/indicators/kuramoto.py`
- **Ricci:** `core/indicators/ricci.py`
- **Entropy:** `core/indicators/entropy.py`
- **DFA:** `core/metrics/dfa.py`
- **Fractal:** `core/metrics/fractal_dimension.py`
