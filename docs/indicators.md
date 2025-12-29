# Indicators

TradePulse exposes a composable feature stack that measures synchronisation,
entropy, fractality, and geometric curvature. All indicators implement the
`BaseFeature` contract and can be orchestrated via `FeatureBlock` pipelines. 【F:core/indicators/base.py†L1-L80】

---

## Feature Architecture

- **`BaseFeature`** – defines the `transform(data, **kwargs)` contract and wraps
  callables so every indicator returns a `FeatureResult` with `value` and
  `metadata`. 【F:core/indicators/base.py†L13-L44】
- **`FeatureBlock`** – executes a list of features sequentially and collates
  their outputs into a mapping, enabling nested/fractal indicator graphs. 【F:core/indicators/base.py†L46-L65】
- **Functional adapters** – wrap legacy functions into features without writing
  new classes via `FunctionalFeature`.

---

## Core Indicators

| Indicator | Purpose | Mathematical Basis | Module |
| --------- | ------- | ------------------ | ------ |
| Kuramoto Order | Phase synchronisation for collective trend detection | Complex order parameter R = \|⟨e^(iθ)⟩\| | [`core/indicators/kuramoto.py`](../core/indicators/kuramoto.py) |
| Entropy & ΔEntropy | Uncertainty quantification and regime transitions | Shannon entropy H = -∑ p log(p) | [`core/indicators/entropy.py`](../core/indicators/entropy.py) |
| Hurst Exponent | Long-term memory and persistence detection | Rescaled range R/S ~ n^H | [`core/indicators/hurst.py`](../core/indicators/hurst.py) |
| Ricci Curvature | Geometric stress in price graph topology | κ = 1 - W₁(μₓ,μᵧ)/d(x,y) | [`core/indicators/ricci.py`](../core/indicators/ricci.py) |
| DFA | Long-range correlation analysis | Fluctuation F(s) ~ s^α | [`core/metrics/dfa.py`](../core/metrics/dfa.py) |
| Fractal Dimension | Self-similarity and complexity | D = lim log N(ε) / log(1/ε) | [`core/metrics/fractal_dimension.py`](../core/metrics/fractal_dimension.py) |
| Hölder Exponent | Local regularity and smoothness | α via wavelet energy scaling | [`core/metrics/holder.py`](../core/metrics/holder.py) |
| Composite Blocks | Multi-metric regime detectors | Combined indicators | [`core/indicators/kuramoto_ricci_composite.py`](../core/indicators/kuramoto_ricci_composite.py) |

### Kuramoto Synchronisation

**Mathematical Foundation:**
The Kuramoto order parameter quantifies phase coherence among N oscillators:
```
R = |Z| / N,  where Z = ∑ⱼ exp(iθⱼ)
```
Equivalently: `R = √[(∑ cos θⱼ)² + (∑ sin θⱼ)²] / N`

**Physical Interpretation:**
- R = 1: Perfect synchronization (all oscillators aligned)
- R ≈ 0.8-1.0: High coherence (strong trending regime)
- R ≈ 0.3-0.7: Partial synchronization (mixed regime)
- R ≈ 0: Desynchronization (random walk regime)

- `compute_phase` extracts instantaneous phase via Hilbert transform (SciPy) or
  a deterministic FFT fallback. 【F:core/indicators/kuramoto.py†L1-L40】
- `kuramoto_order` computes \|mean(exp(iθ))\| to summarise synchrony; higher
  values imply coherent trends. 【F:core/indicators/kuramoto.py†L42-L60】
- Feature wrappers (`KuramotoOrderFeature`, `MultiAssetKuramotoFeature`) expose
  the indicator through the feature pipeline. 【F:core/indicators/kuramoto.py†L91-L111】

**Applications:**
- Multi-asset portfolio regime detection
- Cross-market correlation analysis
- Trend strength quantification
- Regime transition signals (R crossing thresholds)

Usage:

```python
from core.indicators.kuramoto import compute_phase, kuramoto_order
phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])

# Regime detection
if R > 0.7:
    print("Strong trending regime - momentum strategies")
elif R < 0.3:
    print("Random walk regime - market neutral")
```

### Entropy Suite

**Mathematical Foundation:**
Shannon entropy quantifies uncertainty in a probability distribution:
```
H(P) = -∑ᵢ pᵢ · log(pᵢ)  [nats]
```

Delta entropy measures temporal change:
```
ΔH(t) = H(t₂) - H(t₁)
```

**Interpretation:**
- H = 0: Deterministic (constant signal)
- H = log(B): Maximum entropy (uniform distribution over B bins)
- ΔH > 0: Increasing chaos (regime transition signal)
- ΔH < 0: Decreasing chaos (consolidation signal)

- `entropy(series, bins)` normalises data, removes non-finite values, and
  computes Shannon entropy. 【F:core/indicators/entropy.py†L19-L70】
- `delta_entropy(series, window)` compares entropy between consecutive windows
  to detect rising or falling uncertainty. 【F:core/indicators/entropy.py†L72-L120】
- `EntropyFeature` and `DeltaEntropyFeature` wrap both metrics for reuse in
  feature blocks. 【F:core/indicators/entropy.py†L122-L196】

**Applications:**
- Market regime classification
- Volatility regime detection
- Structural break identification
- Complexity analysis

### Hurst Exponent

**Mathematical Foundation:**
The Hurst exponent characterizes long-term memory via scaling:
```
E[R(n)/S(n)] ~ c·n^H
```
Or via lag-differencing: `σ(τ) ~ τ^H`

**Scaling Regimes:**
- H = 0.5: Brownian motion (random walk, efficient market)
- H > 0.5: Persistent (trending, momentum effects)
  * H ∈ [0.55, 0.70]: Moderate trends
  * H > 0.70: Strong persistence
- H < 0.5: Anti-persistent (mean-reverting)
  * H ∈ [0.30, 0.45]: Moderate mean reversion
  * H < 0.30: Strong anti-persistence

- `hurst_exponent(ts, min_lag, max_lag)` runs rescaled-range analysis and clips
  results to `[0, 1]` for stability. 【F:core/indicators/hurst.py†L19-L80】
- `HurstFeature` packages the calculation for downstream orchestration. 【F:core/indicators/hurst.py†L82-L134】

**Applications:**
- Strategy selection (momentum vs mean-reversion)
- Risk management (persistence implies trending risk)
- Market efficiency testing
- Portfolio diversification (different H → different dynamics)

Interpretation:

- `H > 0.5` – persistent/trending regime → momentum strategies
- `H ≈ 0.5` – random walk → market neutral
- `H < 0.5` – anti-persistent, mean-reverting behaviour → mean reversion strategies

### Ricci Curvature

**Mathematical Foundation:**
Ollivier-Ricci curvature measures geometric deformation:
```
κ(x, y) = 1 - W₁(μₓ, μᵧ) / d(x, y)
```
where W₁ is 1-Wasserstein distance and d(x,y) is geodesic distance.

**Curvature Interpretation:**
- κ > 0: Positive curvature (clustering, spherical geometry)
  * Market consolidation, reduced fragmentation
- κ = 0: Flat (Euclidean geometry)
  * Neutral geometric stress
- κ < 0: Negative curvature (dispersion, hyperbolic geometry)
  * Market fragmentation, structural stress, crisis signal

- `build_price_graph` quantises price levels into nodes and connects consecutive
  moves to form an interaction graph. 【F:core/indicators/ricci.py†L268-L318】
- `compute_node_distributions` pre-computes geometry-aware neighbour
  distributions so curvature can be reused across many edges. 【F:core/indicators/ricci.py†L252-L265】
- `ricci_curvature_edge` estimates Ollivier–Ricci curvature using Wasserstein
  distance (SciPy or the in-repo fallback). 【F:core/indicators/ricci.py†L344-L382】
- `mean_ricci` averages curvature across all edges; `MeanRicciFeature` exposes
  it as a feature. 【F:core/indicators/ricci.py†L423-L503】

**Applications:**
- Systemic risk detection (κ ≪ 0 signals fragmentation)
- Market stress indicators
- Regime change detection
- Network-based risk metrics

### DFA (Detrended Fluctuation Analysis)

**Mathematical Foundation:**
DFA estimates long-range correlations via scaling exponent α:
```
F(s) ~ s^α
```
where F(s) is the RMS fluctuation at scale s.

**Scaling Exponent α:**
- α = 0.5: White noise (uncorrelated)
- α < 0.5: Anti-correlated (mean-reverting)
- α > 0.5: Long-range correlations (persistent)
- α ≈ 1.0: 1/f noise (pink noise, scale-invariant)
- α ≈ 1.5: Brownian motion

**Relationship:** For stationary processes, α ≈ H (Hurst exponent).

### Fractal Dimension

**Mathematical Foundation:**
Box-counting dimension quantifies self-similarity:
```
D = lim_{ε→0} [log N(ε) / log(1/ε)]
```
where N(ε) is the number of boxes of size ε needed to cover the set.

**Interpretation:**
- D = 1.0: Smooth curve (Euclidean)
- D ≈ 1.5: Brownian motion (typical for finance)
- D → 2.0: Highly irregular, space-filling

**Applications:**
- Complexity quantification
- Volatility regime classification
- Market efficiency analysis

### Hölder Exponent

**Mathematical Foundation:**
Measures local regularity via wavelet coefficient scaling:
```
|d_j| ~ 2^{j(α + 1/2)}
```
where α is the Hölder exponent.

**Regularity Regimes:**
- α > 1: Differentiable (smooth)
- α = 1: Lipschitz continuous
- 0 < α < 1: Hölder continuous but not differentiable
- α = 0.5: Brownian-like roughness
- α < 0.5: Very rough, singular

**Multifractal Analysis:**
The singularity spectrum f(α) characterizes the distribution of local regularities.
Width Δα = α_max - α_min quantifies multifractality.

### Composite Patterns

`core/indicators/kuramoto_ricci_composite.py` demonstrates how to combine the
above primitives into higher-level signals (e.g., synchrony + curvature) for use
in regime classification or agent routing. Consult the source when designing new
blocks so naming and metadata remain consistent.

**Example Composite Indicators:**
- **Trend Strength:** Combine Kuramoto R with Hurst H
  * High R + High H → Strong persistent trend
  * Low R + H ≈ 0.5 → Random walk
  * High R + Low H → Mean-reverting consolidation

- **Regime Detector:** Combine Entropy, Hurst, Ricci
  * Low H, High ΔH, Negative κ → Regime transition
  * High H, Low ΔH, Positive κ → Stable trending
  * H ≈ 0.5, Low ΔH, κ ≈ 0 → Efficient market

---

## Building Custom Pipelines

```python
from core.indicators.base import FeatureBlock
from core.indicators.kuramoto import KuramotoOrderFeature
from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature

regime_block = FeatureBlock(
    name="market_regime",
    features=[
        KuramotoOrderFeature(name="R"),
        EntropyFeature(bins=40, name="H"),
        HurstFeature(name="hurst")
    ],
)
features = regime_block.transform(prices)

# Regime classification
if features["R"] > 0.7 and features["hurst"] > 0.6:
    regime = "strong_trend"
elif features["H"] > 2.0 and features["hurst"] < 0.4:
    regime = "mean_reverting_chaos"
elif abs(features["hurst"] - 0.5) < 0.1:
    regime = "random_walk"
```

- Use descriptive feature names so downstream agents (`StrategySignature`) can
  align metrics with their expectations.
- Nest blocks (a block can register another block) to mirror the fractal phase →
  regime → policy architecture described in the FPM-A guide.

---

## Mathematical Relationships

### Cross-Indicator Connections

1. **Hurst ↔ DFA:** For stationary series, H ≈ α (DFA exponent)
2. **Hurst ↔ Fractal Dimension:** D = 2 - H (for 1D embeddings)
3. **Hölder ↔ Hurst:** α_global ≈ H for self-affine processes
4. **Entropy ↔ Complexity:** High H often correlates with high fractal dimension
5. **Kuramoto ↔ Hurst:** High R suggests H > 0.5 (persistent synchronization)

### Regime Detection Matrix

| Regime | Kuramoto R | Hurst H | Entropy ΔH | Ricci κ |
|--------|-----------|---------|------------|---------|
| Strong Trend | > 0.7 | > 0.6 | < 0 | > 0 |
| Random Walk | 0.2-0.5 | 0.45-0.55 | ≈ 0 | ≈ 0 |
| Mean Reversion | 0.3-0.6 | < 0.4 | < 0 | > 0 |
| Regime Transition | Variable | Variable | > 0.5 | < 0 |
| Crisis/Fragmentation | < 0.3 | Variable | > 1.0 | ≪ 0 |

---

## Performance Considerations

All indicators support:
- **GPU Acceleration:** CuPy/CUDA backends for large datasets
- **Memory Efficiency:** float32 mode, chunked processing
- **Parallel Execution:** Multi-core processing via Numba
- **Numerical Stability:** Defensive programming against NaN/Inf

Backend selection is automatic based on data size and hardware availability.

---

## References

- **Kuramoto:** Acebrón et al. (2005). The Kuramoto model. Rev. Mod. Phys.
- **Entropy:** Shannon (1948). A mathematical theory of communication.
- **Hurst:** Hurst (1951). Long-term storage capacity of reservoirs.
- **Ricci:** Ollivier (2009). Ricci curvature of Markov chains.
- **DFA:** Peng et al. (1994). Mosaic organization of DNA nucleotides.
- **Fractal:** Mandelbrot (1982). The Fractal Geometry of Nature.
- **Hölder:** Jaffard (2004). Wavelet techniques in multifractal analysis.

For complete mathematical foundations, see [`docs/math.md`](./math.md).
