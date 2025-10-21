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

| Indicator | Purpose | Module |
| --------- | ------- | ------ |
| Kuramoto Order | Measures phase synchronisation to gauge collective trend agreement. | [`core/indicators/kuramoto.py`](../core/indicators/kuramoto.py) |
| Entropy & ΔEntropy | Quantifies randomness and regime transitions in price data. | [`core/indicators/entropy.py`](../core/indicators/entropy.py) |
| Hurst Exponent | Detects persistence vs. mean reversion using R/S analysis. | [`core/indicators/hurst.py`](../core/indicators/hurst.py) |
| Ricci Curvature | Captures geometric deformation of the price graph to flag stress. | [`core/indicators/ricci.py`](../core/indicators/ricci.py) |
| Composite Blocks | Combine multiple features into regime detectors or policies. | [`core/indicators/kuramoto_ricci_composite.py`](../core/indicators/kuramoto_ricci_composite.py) |

### Kuramoto Synchronisation

- `compute_phase` extracts instantaneous phase via Hilbert transform (SciPy) or
  a deterministic FFT fallback. 【F:core/indicators/kuramoto.py†L1-L40】
- `kuramoto_order` computes \|mean(exp(iθ))\| to summarise synchrony; higher
  values imply coherent trends. 【F:core/indicators/kuramoto.py†L42-L60】
- Feature wrappers (`KuramotoOrderFeature`, `MultiAssetKuramotoFeature`) expose
  the indicator through the feature pipeline. 【F:core/indicators/kuramoto.py†L91-L111】

Usage:

```python
from core.indicators.kuramoto import compute_phase, kuramoto_order
phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])
```

### Entropy Suite

- `entropy(series, bins)` normalises data, removes non-finite values, and
  computes Shannon entropy. 【F:core/indicators/entropy.py†L19-L70】
- `delta_entropy(series, window)` compares entropy between consecutive windows
  to detect rising or falling uncertainty. 【F:core/indicators/entropy.py†L72-L120】
- `EntropyFeature` and `DeltaEntropyFeature` wrap both metrics for reuse in
  feature blocks. 【F:core/indicators/entropy.py†L122-L196】

### Hurst Exponent

- `hurst_exponent(ts, min_lag, max_lag)` runs rescaled-range analysis and clips
  results to `[0, 1]` for stability. 【F:core/indicators/hurst.py†L19-L80】
- `HurstFeature` packages the calculation for downstream orchestration. 【F:core/indicators/hurst.py†L82-L134】

Interpretation:

- `H > 0.5` – persistent/trending regime
- `H ≈ 0.5` – random walk
- `H < 0.5` – anti-persistent, mean-reverting behaviour

### Ricci Curvature

- `build_price_graph` quantises price levels into nodes and connects consecutive
  moves to form an interaction graph. 【F:core/indicators/ricci.py†L268-L318】
- `compute_node_distributions` pre-computes geometry-aware neighbour
  distributions so curvature can be reused across many edges. 【F:core/indicators/ricci.py†L252-L265】
- `ricci_curvature_edge` estimates Ollivier–Ricci curvature using Wasserstein
  distance (SciPy or the in-repo fallback). 【F:core/indicators/ricci.py†L344-L382】
- `mean_ricci` averages curvature across all edges; `MeanRicciFeature` exposes
  it as a feature. 【F:core/indicators/ricci.py†L423-L503】

### Composite Patterns

`core/indicators/kuramoto_ricci_composite.py` demonstrates how to combine the
above primitives into higher-level signals (e.g., synchrony + curvature) for use
in regime classification or agent routing. Consult the source when designing new
blocks so naming and metadata remain consistent.

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
```

- Use descriptive feature names so downstream agents (`StrategySignature`) can
  align metrics with their expectations.
- Nest blocks (a block can register another block) to mirror the fractal phase →
  regime → policy architecture described in the FPM-A guide.
