# Mathematical Inventory (Phase 0.5 Evidence-Hardened)

This inventory enumerates math-bearing components discovered in the current codebase. Every statement is evidence-anchored to code locations.

## Scope
- `core/indicators/`
- `core/neuro/`
- `execution/risk/`
- `src/geosync/core/neuro/`
- `src/geosync/features/`
- `src/geosync/protocol/`
- `src/geosync/regime/`
- `src/geosync/risk/`
- `src/geosync/utils/`

---

## Core Indicators (`core/indicators`)

### Kuramoto phase + order parameter (`core/indicators/kuramoto.py`)
- **Symbolic name:** Observed in code: analytic signal phase \(\theta(t) = \arg(x + i\,\mathcal{H}\{x\})\) and Kuramoto order parameter \(R = |\frac{1}{N}\sum e^{i\theta_j}|\). (core/indicators/kuramoto.py:245-319, 397-483)
- **Code location(s):** `core/indicators/kuramoto.py` (functions and features), `core/indicators/trading.py` (wrappers). (core/indicators/kuramoto.py:1-772; core/indicators/trading.py:1-630)
- **Type:** Observed in code: deterministic, discrete-time transforms on arrays. (core/indicators/kuramoto.py:245-562)
- **Inputs/outputs:** Observed in code: 1D/2D arrays of real/complex phases, optional weights; outputs are phase arrays and \(R\) scalars/series. (core/indicators/kuramoto.py:245-562, 397-520)
- **Implicit assumptions:** Observed in code: input arrays are 1D or 2D and finite after sanitization; weights broadcastable and non-negative. (core/indicators/kuramoto.py:332-351, 492-547)
- **Known or suspected weaknesses:** Observed in code: denormal suppression (1e-8) and clipping to \([0,1]\) for \(R\). (core/indicators/kuramoto.py:142-147, 204-211, 454-480)

EVIDENCE:
- Functions: `compute_phase`, `kuramoto_order`, `_kuramoto_order_jit`, `_kuramoto_order_2d_jit`, `multi_asset_kuramoto`, `compute_phase_gpu`. (core/indicators/kuramoto.py:78-744)
- Constants/thresholds: denormal threshold `1e-8` and clamp to `1.0`. (core/indicators/kuramoto.py:142-147, 204-211, 454-480)
- Backend selection logic: SciPy fast-path, NumPy FFT fallback, CuPy GPU path. (core/indicators/kuramoto.py:344-387, 623-666)
- Input validation: 1D/2D checks and `out` shape/dtype checks. (core/indicators/kuramoto.py:334-341, 492-512)

MATH CONTRACT:
- **Definition:** Observed in code: phase from analytic signal and order parameter from cosine/sine aggregation. (core/indicators/kuramoto.py:245-319, 397-419)
- **Domain:** Observed in code: `compute_phase` expects 1D array and validates `out` shape/dtype; `kuramoto_order` expects 1D or 2D array. (core/indicators/kuramoto.py:334-341, 492-512)
- **Range:** Observed in code: \(R\) clipped to \([0,1]\) with denormal suppression to 0.0. (core/indicators/kuramoto.py:142-147, 204-211, 454-480)
- **Invariants:** Observed in code: non-finite inputs excluded from aggregation. (core/indicators/kuramoto.py:129-137, 514-519)
- **Failure modes:** Observed in code: empty arrays return 0.0 or empty arrays; invalid shapes raise `ValueError`. (core/indicators/kuramoto.py:120-137, 334-341, 492-512, 354-356)
- **Approximation notes:** Observed in code: Hilbert transform computed via FFT-based approximation when SciPy unavailable. (core/indicators/kuramoto.py:268-387)
- **Complexity:** Observed in code: O(N log N) for Hilbert transform, O(N·T) for order parameter. (core/indicators/kuramoto.py:299-301, 458-460)
- **Determinism:** Observed in code: no RNG usage in phase/order parameter functions. (core/indicators/kuramoto.py:245-562)

### Multi-scale Kuramoto synchronization (`core/indicators/multiscale_kuramoto.py`)
- **Symbolic name:** Observed in code: per-timeframe Kuramoto order parameter and cross-scale coherence with consensus \(R\). (core/indicators/multiscale_kuramoto.py:42-118, 400-520)
- **Code location(s):** `core/indicators/multiscale_kuramoto.py`. (core/indicators/multiscale_kuramoto.py:1-768)
- **Type:** Observed in code: deterministic, discrete-time resampling and aggregation. (core/indicators/multiscale_kuramoto.py:90-210, 400-650)
- **Inputs/outputs:** Observed in code: `DatetimeIndex` price series; outputs `MultiScaleResult` with consensus and coherence. (core/indicators/multiscale_kuramoto.py:90-160, 430-520)
- **Implicit assumptions:** Observed in code: `DatetimeIndex` required for resampling; forward-fill used. (core/indicators/multiscale_kuramoto.py:99-124, 146-169)
- **Known or suspected weaknesses:** Observed in code: resampling forward-fill determines derived series. (core/indicators/multiscale_kuramoto.py:146-169)

EVIDENCE:
- Functions/classes: `FractalResampler`, `MultiScaleKuramoto`, `TimeFrame`, `MultiScaleResult`. (core/indicators/multiscale_kuramoto.py:35-520)
- Constants/thresholds: timeframe enum values (seconds). (core/indicators/multiscale_kuramoto.py:40-68)
- Backend selection logic: optional SciPy signal module imported and used when available. (core/indicators/multiscale_kuramoto.py:28-34, 280-310)
- Input validation: `DatetimeIndex` enforced in `FractalResampler.__post_init__`. (core/indicators/multiscale_kuramoto.py:99-108)

MATH CONTRACT:
- **Definition:** Observed in code: compute per-timeframe Kuramoto \(R\) and cross-scale coherence from resampled series. (core/indicators/multiscale_kuramoto.py:400-520)
- **Domain:** Observed in code: `DatetimeIndex` series, resample frequencies from `TimeFrame`. (core/indicators/multiscale_kuramoto.py:99-124, 40-68)
- **Range:** Observed in code: coherence and \(R\) values are derived from cos/sin aggregation and clipped in underlying Kuramoto computations. (core/indicators/multiscale_kuramoto.py:400-520; core/indicators/kuramoto.py:142-147, 204-211)
- **Invariants:** Observed in code: cached resamples reused for deterministic reuse ratio. (core/indicators/multiscale_kuramoto.py:123-209)
- **Failure modes:** Observed in code: resampling errors may raise `ValueError` when `strict=True`. (core/indicators/multiscale_kuramoto.py:186-205)
- **Approximation notes:** Observed in code: uses resampling + last/ffill to construct coarser series. (core/indicators/multiscale_kuramoto.py:146-169)
- **Complexity:** Observed in code: resample loops over requested timeframes. (core/indicators/multiscale_kuramoto.py:173-205)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/multiscale_kuramoto.py:1-520)

### Ricci curvature on price graphs (`core/indicators/ricci.py`)
- **Symbolic name:** Observed in code: Ollivier–Ricci curvature proxy and Wasserstein-1 computation. (core/indicators/ricci.py:535-678, 823-852)
- **Code location(s):** `core/indicators/ricci.py`. (core/indicators/ricci.py:1-1020)
- **Type:** Observed in code: deterministic, graph-based discrete-time computation. (core/indicators/ricci.py:450-980)
- **Inputs/outputs:** Observed in code: price arrays, graph parameters; outputs mean curvature. (core/indicators/ricci.py:450-980)
- **Implicit assumptions:** Observed in code: graph structure built from price similarity; Wasserstein computed on local distributions. (core/indicators/ricci.py:450-852)
- **Known or suspected weaknesses:** Observed in code: simplified graph fallback if `networkx` is unavailable. (core/indicators/ricci.py:64-182)

EVIDENCE:
- Functions/classes: `build_price_graph`, `ricci_curvature_edge`, `mean_ricci`, `MeanRicciFeature`. (core/indicators/ricci.py:450-980)
- Constants/thresholds: none defined at module scope; thresholds are parameters. (core/indicators/ricci.py:450-980)
- Backend selection logic: `networkx` import fallback to `_SimpleGraph`. (core/indicators/ricci.py:64-182)
- Input validation: parameter checks in `NodeDistribution.__post_init__`. (core/indicators/ricci.py:335-360)

MATH CONTRACT:
- **Definition:** Observed in code: curvature uses Wasserstein distance between node distributions, \(\kappa=1-W/ d\). (core/indicators/ricci.py:535-678, 823-852)
- **Domain:** Observed in code: graph nodes with non-negative weights; distributions normalized. (core/indicators/ricci.py:335-439)
- **Range:** Not in code; removed. (core/indicators/ricci.py:1-1020)
- **Invariants:** Observed in code: distributions normalized and non-negative. (core/indicators/ricci.py:376-439)
- **Failure modes:** Observed in code: fallback path for missing `networkx`; shortest-path fallback for disconnections. (core/indicators/ricci.py:64-182, 640-675)
- **Approximation notes:** Observed in code: Wasserstein approximation via local distributions and shortest paths. (core/indicators/ricci.py:535-678)
- **Complexity:** Observed in code: comments indicate O(N·T) for W1 kernel; loops over edges. (core/indicators/ricci.py:200-276, 678-760)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/ricci.py:1-980)

### Temporal Ricci curvature (`core/indicators/temporal_ricci.py`)
- **Symbolic name:** Observed in code: temporal curvature and topological transition score from rolling graph snapshots. (core/indicators/temporal_ricci.py:347-650)
- **Code location(s):** `core/indicators/temporal_ricci.py`. (core/indicators/temporal_ricci.py:1-683)
- **Type:** Observed in code: deterministic, discrete-time rolling estimator. (core/indicators/temporal_ricci.py:347-650)
- **Inputs/outputs:** Observed in code: price series and optional volume; outputs `TemporalRicciResult`. (core/indicators/temporal_ricci.py:347-520)
- **Implicit assumptions:** Observed in code: discretization into price bins; graph edges from proximity. (core/indicators/temporal_ricci.py:240-340, 347-520)
- **Known or suspected weaknesses:** Observed in code: lightweight graph and Ollivier–Ricci proxy. (core/indicators/temporal_ricci.py:152-330)

EVIDENCE:
- Functions/classes: `LightGraph`, `OllivierRicciCurvatureLite`, `PriceLevelGraph`, `TemporalRicciAnalyzer`. (core/indicators/temporal_ricci.py:34-520)
- Constants/thresholds: `_VOLUME_MODES`. (core/indicators/temporal_ricci.py:24-26)
- Backend selection logic: optional `networkx` fallback in `_shortest_path_length`. (core/indicators/temporal_ricci.py:176-225)
- Input validation: volume mode checks and parameter validation in analyzer. (core/indicators/temporal_ricci.py:347-430)

MATH CONTRACT:
- **Definition:** Observed in code: compute curvature on rolling graphs and aggregate to temporal curvature and transition score. (core/indicators/temporal_ricci.py:347-520)
- **Domain:** Observed in code: price arrays converted to bins; volume mode in `_VOLUME_MODES`. (core/indicators/temporal_ricci.py:24-26, 347-430)
- **Range:** Not in code; removed. (core/indicators/temporal_ricci.py:1-683)
- **Invariants:** Observed in code: graph edges are undirected and weights non-negative. (core/indicators/temporal_ricci.py:52-75)
- **Failure modes:** Observed in code: empty graphs or missing edges yield trivial curvature outputs. (core/indicators/temporal_ricci.py:380-430)
- **Approximation notes:** Observed in code: Ollivier–Ricci approximation via lazy random walks and shortest paths. (core/indicators/temporal_ricci.py:152-225)
- **Complexity:** Not in code; removed. (core/indicators/temporal_ricci.py:1-683)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/temporal_ricci.py:1-520)

### Kuramoto–Ricci composite regime classifier (`core/indicators/kuramoto_ricci_composite.py`)
- **Symbolic name:** Observed in code: rule-based phase classifier and signals derived from \(R\), coherence, curvature, and transition score. (core/indicators/kuramoto_ricci_composite.py:34-200)
- **Code location(s):** `core/indicators/kuramoto_ricci_composite.py`. (core/indicators/kuramoto_ricci_composite.py:1-320)
- **Type:** Observed in code: deterministic decision logic. (core/indicators/kuramoto_ricci_composite.py:34-200)
- **Inputs/outputs:** Observed in code: `MultiScaleResult`, `TemporalRicciResult`, static Ricci; outputs `CompositeSignal`. (core/indicators/kuramoto_ricci_composite.py:106-200)
- **Implicit assumptions:** Observed in code: fixed threshold parameters passed at initialization. (core/indicators/kuramoto_ricci_composite.py:44-70)
- **Known or suspected weaknesses:** Observed in code: threshold-based logic (PROXY for continuous dynamics). (core/indicators/kuramoto_ricci_composite.py:72-151)

EVIDENCE:
- Functions/classes: `KuramotoRicciComposite`, `CompositeSignal`, `MarketPhase`. (core/indicators/kuramoto_ricci_composite.py:18-200)
- Constants/thresholds: default thresholds in `KuramotoRicciComposite.__init__`. (core/indicators/kuramoto_ricci_composite.py:44-70)
- Backend selection logic: none observed. (core/indicators/kuramoto_ricci_composite.py:1-200)
- Input validation: none observed. (core/indicators/kuramoto_ricci_composite.py:1-200)

MATH CONTRACT:
- **Definition:** Observed in code: phase = rule on \(R\), curvature, transition; confidence/entry/exit/risk computed via piecewise formulas. (core/indicators/kuramoto_ricci_composite.py:72-151)
- **Domain:** Observed in code: expects scalar metrics from upstream results. (core/indicators/kuramoto_ricci_composite.py:106-140)
- **Range:** Observed in code: confidence, entry, exit, risk are clipped to fixed bounds. (core/indicators/kuramoto_ricci_composite.py:86-151)
- **Invariants:** Observed in code: output signal fields populated for every call. (core/indicators/kuramoto_ricci_composite.py:106-140)
- **Failure modes:** Not in code; removed. (core/indicators/kuramoto_ricci_composite.py:1-320)
- **Approximation notes:** PROXY: phase classification uses threshold logic rather than continuous model. (core/indicators/kuramoto_ricci_composite.py:72-151)
- **Complexity:** Not in code; removed. (core/indicators/kuramoto_ricci_composite.py:1-320)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/kuramoto_ricci_composite.py:1-200)

### Hurst exponent (`core/indicators/hurst.py`)
- **Symbolic name:** Observed in code: Hurst exponent from lag-differencing regression \(\log \sigma(\tau) = H\log \tau + c\). (core/indicators/hurst.py:1-60, 352-450)
- **Code location(s):** `core/indicators/hurst.py`, wrappers in `core/indicators/trading.py`. (core/indicators/hurst.py:1-639; core/indicators/trading.py:451-504)
- **Type:** Observed in code: deterministic estimator with optional Numba/CUDA backends. (core/indicators/hurst.py:1-220, 352-450)
- **Inputs/outputs:** Observed in code: 1D arrays; outputs \(H\). (core/indicators/hurst.py:352-450)
- **Implicit assumptions:** Observed in code: lags in a fixed range; input length sufficient. (core/indicators/hurst.py:352-430)
- **Known or suspected weaknesses:** Observed in code: backend selection depends on thresholds. (core/indicators/hurst.py:110-140)

EVIDENCE:
- Functions/classes: `hurst_exponent`, `_compute_tau_numba`, `_compute_tau_cuda_kernel`, `HurstFeature`. (core/indicators/hurst.py:92-560)
- Constants/thresholds: `_DEFAULT_MIN_LAG`, `_DEFAULT_MAX_LAG`, `_NUMBA_AUTO_THRESHOLD`, `_CUDA_AUTO_THRESHOLD`. (core/indicators/hurst.py:44-55, 74-88)
- Backend selection logic: `_numba_available`, `_cuda_available`, backend selection in `hurst_exponent`. (core/indicators/hurst.py:92-140, 352-450)
- Input validation: checks on lags and input sizes in `hurst_exponent`. (core/indicators/hurst.py:352-430)

MATH CONTRACT:
- **Definition:** Observed in code: regression of \(\log \sigma(\tau)\) on \(\log \tau\) for H. (core/indicators/hurst.py:352-430)
- **Domain:** Observed in code: 1D arrays; lags positive. (core/indicators/hurst.py:352-430)
- **Range:** Observed in code: H is clipped to [0, 1]. (core/indicators/hurst.py:430-450)
- **Invariants:** Observed in code: NaNs filtered before regression. (core/indicators/hurst.py:392-410)
- **Failure modes:** Observed in code: returns 0.5 for insufficient data. (core/indicators/hurst.py:376-390)
- **Approximation notes:** Observed in code: lag-differencing estimator (proxy for R/S). (core/indicators/hurst.py:1-60, 352-430)
- **Complexity:** Observed in code: comments describe O(N·L). (core/indicators/hurst.py:26-28)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/hurst.py:1-450)

### Shannon entropy (`core/indicators/entropy.py`)
- **Symbolic name:** Observed in code: Shannon entropy \(H = -\sum p_i \log p_i\). (core/indicators/entropy.py:85-170)
- **Code location(s):** `core/indicators/entropy.py`. (core/indicators/entropy.py:1-742)
- **Type:** Observed in code: deterministic histogram estimator with optional CPU/GPU backends. (core/indicators/entropy.py:85-474)
- **Inputs/outputs:** Observed in code: 1D arrays, bin count, backend selector; output scalar entropy. (core/indicators/entropy.py:85-170, 325-474)
- **Implicit assumptions:** Observed in code: inputs are finite after filtering; histogram discretization used. (core/indicators/entropy.py:180-220)
- **Known or suspected weaknesses:** Observed in code: backend selection depends on data size thresholds. (core/indicators/entropy.py:305-355)

EVIDENCE:
- Functions/classes: `entropy`, `delta_entropy`, `EntropyFeature`, `DeltaEntropyFeature`. (core/indicators/entropy.py:85-719)
- Constants/thresholds: `_GPU_MIN_SIZE_BYTES`, `_GPU_MEMORY_MARGIN`. (core/indicators/entropy.py:45-52)
- Backend selection logic: `_resolve_backend`, `_entropy_gpu`. (core/indicators/entropy.py:325-412)
- Input validation: empty array checks and finite filtering. (core/indicators/entropy.py:180-220)

MATH CONTRACT:
- **Definition:** Observed in code: Shannon entropy via histogram-based probability mass. (core/indicators/entropy.py:85-170)
- **Domain:** Observed in code: 1D numeric arrays; bins positive. (core/indicators/entropy.py:85-170)
- **Range:** Observed in code: returns 0.0 for empty/invalid inputs. (core/indicators/entropy.py:180-220)
- **Invariants:** Observed in code: probabilities normalized and zero-prob bins excluded. (core/indicators/entropy.py:220-290)
- **Failure modes:** Observed in code: returns 0.0 if no valid data remains. (core/indicators/entropy.py:180-220)
- **Approximation notes:** Observed in code: histogram discretization and chunked averaging. (core/indicators/entropy.py:85-170, 412-474)
- **Complexity:** Observed in code: O(N + B). (core/indicators/entropy.py:112-120)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/entropy.py:1-474)

### Pivot detection and divergence (`core/indicators/pivot_detection.py`)
- **Symbolic name:** Observed in code: pivot highs/lows and divergence detection between series. (core/indicators/pivot_detection.py:27-260)
- **Code location(s):** `core/indicators/pivot_detection.py`. (core/indicators/pivot_detection.py:1-378)
- **Type:** Observed in code: deterministic, discrete-time pattern detection. (core/indicators/pivot_detection.py:27-260)
- **Inputs/outputs:** Observed in code: price/indicator series, window parameters; outputs pivot lists and divergence signals. (core/indicators/pivot_detection.py:40-260)
- **Implicit assumptions:** Observed in code: `left/right` positive; series 1D; timestamps aligned. (core/indicators/pivot_detection.py:68-104, 154-182)
- **Known or suspected weaknesses:** Observed in code: tolerance and window parameters are fixed inputs. (core/indicators/pivot_detection.py:68-104)

EVIDENCE:
- Functions/classes: `detect_pivots`, `detect_pivot_divergences`, `PivotPoint`, `PivotDivergenceSignal`. (core/indicators/pivot_detection.py:27-260)
- Constants/thresholds: default `left/right/tolerance` in function signatures. (core/indicators/pivot_detection.py:58-66, 154-168)
- Backend selection logic: none observed. (core/indicators/pivot_detection.py:1-260)
- Input validation: checks for window sizes, 1D arrays, timestamp length. (core/indicators/pivot_detection.py:68-104, 154-182)

MATH CONTRACT:
- **Definition:** Observed in code: pivot = local extrema in window; divergence = opposing pivot moves. (core/indicators/pivot_detection.py:111-260)
- **Domain:** Observed in code: 1D arrays, positive window parameters. (core/indicators/pivot_detection.py:68-104, 154-182)
- **Range:** Not in code; removed. (core/indicators/pivot_detection.py:1-378)
- **Invariants:** Observed in code: pivot indices strictly increasing (append in scan order). (core/indicators/pivot_detection.py:111-142)
- **Failure modes:** Observed in code: raises `ValueError` on invalid parameters. (core/indicators/pivot_detection.py:68-104, 154-182)
- **Approximation notes:** PROXY: pivot detection uses fixed window and tolerance parameters. (core/indicators/pivot_detection.py:58-66, 154-168)
- **Complexity:** Not in code; removed. (core/indicators/pivot_detection.py:1-378)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/pivot_detection.py:1-260)

### Indicator normalization (`core/indicators/normalization.py`)
- **Symbolic name:** Observed in code: z-score and min-max normalization. (core/indicators/normalization.py:34-122)
- **Code location(s):** `core/indicators/normalization.py`. (core/indicators/normalization.py:1-172)
- **Type:** Observed in code: deterministic, discrete-time transformation. (core/indicators/normalization.py:34-122)
- **Inputs/outputs:** Observed in code: 1D arrays; outputs normalized arrays. (core/indicators/normalization.py:48-122)
- **Implicit assumptions:** Observed in code: input is 1D; epsilon > 0; feature_range high>low. (core/indicators/normalization.py:34-72)
- **Known or suspected weaknesses:** Observed in code: zero variance returns zeros or midpoint. (core/indicators/normalization.py:61-88)

EVIDENCE:
- Functions/classes: `normalize_indicator_series`, `IndicatorNormalizationConfig`. (core/indicators/normalization.py:34-155)
- Constants/thresholds: `epsilon`, `feature_range` in config. (core/indicators/normalization.py:34-72)
- Backend selection logic: none observed. (core/indicators/normalization.py:1-155)
- Input validation: 1D check, epsilon and range validation. (core/indicators/normalization.py:34-72, 75-90)

MATH CONTRACT:
- **Definition:** Observed in code: z-score \((x-\mu)/\sigma\) or min-max scaling. (core/indicators/normalization.py:61-122)
- **Domain:** Observed in code: 1D arrays; epsilon>0 and range high>low. (core/indicators/normalization.py:34-72)
- **Range:** Observed in code: min-max maps to configured range; z-score unbounded. (core/indicators/normalization.py:61-122)
- **Invariants:** Observed in code: output shape matches input shape. (core/indicators/normalization.py:75-122)
- **Failure modes:** Observed in code: invalid shape raises `ValueError`. (core/indicators/normalization.py:52-59)
- **Approximation notes:** Not in code; removed. (core/indicators/normalization.py:1-172)
- **Complexity:** Not in code; removed. (core/indicators/normalization.py:1-172)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/normalization.py:1-122)

### Ensemble divergence aggregation (`core/indicators/ensemble_divergence.py`)
- **Symbolic name:** Observed in code: weighted consensus score from divergence signals. (core/indicators/ensemble_divergence.py:51-200)
- **Code location(s):** `core/indicators/ensemble_divergence.py`. (core/indicators/ensemble_divergence.py:1-290)
- **Type:** Observed in code: deterministic aggregation. (core/indicators/ensemble_divergence.py:86-200)
- **Inputs/outputs:** Observed in code: list of `IndicatorDivergenceSignal` to `EnsembleDivergenceResult`. (core/indicators/ensemble_divergence.py:86-200)
- **Implicit assumptions:** Observed in code: confidences in \([0,1]\), strengths non-negative. (core/indicators/ensemble_divergence.py:31-68)
- **Known or suspected weaknesses:** Observed in code: threshold gating via `min_support` and `min_consensus`. (core/indicators/ensemble_divergence.py:86-150)

EVIDENCE:
- Functions/classes: `compute_ensemble_divergence`, `IndicatorDivergenceSignal`, `EnsembleDivergenceResult`. (core/indicators/ensemble_divergence.py:10-250)
- Constants/thresholds: `min_support`, `min_consensus` defaults. (core/indicators/ensemble_divergence.py:86-110)
- Backend selection logic: none observed. (core/indicators/ensemble_divergence.py:1-250)
- Input validation: validation in dataclasses and parameter checks. (core/indicators/ensemble_divergence.py:31-68, 102-122)

MATH CONTRACT:
- **Definition:** Observed in code: weighted aggregation with consensus gating and squashing. (core/indicators/ensemble_divergence.py:130-210)
- **Domain:** Observed in code: positive strength, confidence in [0,1]. (core/indicators/ensemble_divergence.py:31-68)
- **Range:** Observed in code: score in [-1,1] via `_squash`. (core/indicators/ensemble_divergence.py:176-210, 250-270)
- **Invariants:** Observed in code: empty inputs yield neutral result. (core/indicators/ensemble_divergence.py:118-128)
- **Failure modes:** Observed in code: invalid parameters raise `ValueError`. (core/indicators/ensemble_divergence.py:102-122)
- **Approximation notes:** PROXY: consensus gating uses thresholds. (core/indicators/ensemble_divergence.py:86-150)
- **Complexity:** Not in code; removed. (core/indicators/ensemble_divergence.py:1-290)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/ensemble_divergence.py:1-210)

### Hierarchical feature computation (`core/indicators/hierarchical_features.py`)
- **Symbolic name:** Observed in code: entropy, Hurst, Kuramoto, and microstructure features computed per timeframe. (core/indicators/hierarchical_features.py:88-260)
- **Code location(s):** `core/indicators/hierarchical_features.py`. (core/indicators/hierarchical_features.py:1-293)
- **Type:** Observed in code: deterministic, discrete-time aggregation. (core/indicators/hierarchical_features.py:88-260)
- **Inputs/outputs:** Observed in code: OHLCV frames by timeframe; returns structured feature map. (core/indicators/hierarchical_features.py:88-260)
- **Implicit assumptions:** Observed in code: `close` column exists and indices are datetimes. (core/indicators/hierarchical_features.py:116-140)
- **Known or suspected weaknesses:** Observed in code: fixed entropy bin count constants. (core/indicators/hierarchical_features.py:46-52)

EVIDENCE:
- Functions/classes: `compute_hierarchical_features`, `_shannon_entropy`, `FeatureBufferCache`. (core/indicators/hierarchical_features.py:30-260)
- Constants/thresholds: `_ENTROPY_BIN_COUNT`, `_ENTROPY_SCALE`, `_ENTROPY_CLIP`. (core/indicators/hierarchical_features.py:46-52)
- Backend selection logic: none observed. (core/indicators/hierarchical_features.py:1-260)
- Input validation: non-empty inputs; datetime index enforcement. (core/indicators/hierarchical_features.py:107-130)

MATH CONTRACT:
- **Definition:** Observed in code: entropy via histogram counts, Kuramoto via phase aggregation, Hurst via `hurst_exponent`. (core/indicators/hierarchical_features.py:46-260)
- **Domain:** Observed in code: OHLCV frames with `close` column; non-empty reference timeframe. (core/indicators/hierarchical_features.py:107-130)
- **Range:** Observed in code: entropy returns 0.0 on invalid input; Kuramoto clipped via underlying functions. (core/indicators/hierarchical_features.py:46-80, 170-210; core/indicators/kuramoto.py:142-147)
- **Invariants:** Observed in code: cache buffers reused per key. (core/indicators/hierarchical_features.py:20-44)
- **Failure modes:** Observed in code: `ValueError` on empty inputs. (core/indicators/hierarchical_features.py:107-130)
- **Approximation notes:** PROXY: entropy uses fixed bins. (core/indicators/hierarchical_features.py:46-80)
- **Complexity:** Not in code; removed. (core/indicators/hierarchical_features.py:1-293)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/hierarchical_features.py:1-260)

### Fractal GCL helpers (`core/indicators/fractal_gcl.py`)
- **Symbolic name:** Observed in code: fractal dimension estimate and contrastive loss with temperature \(\tau\). (core/indicators/fractal_gcl.py:10-90)
- **Code location(s):** `core/indicators/fractal_gcl.py`. (core/indicators/fractal_gcl.py:1-108)
- **Type:** Observed in code: deterministic for FD/novelty; stochastic when used with training elsewhere. (core/indicators/fractal_gcl.py:10-90)
- **Inputs/outputs:** Observed in code: networkx graphs and embeddings; outputs novelty and FD or loss tensor. (core/indicators/fractal_gcl.py:10-90)
- **Implicit assumptions:** Observed in code: embeddings are 2D arrays with matching dimension. (core/indicators/fractal_gcl.py:67-78)
- **Known or suspected weaknesses:** Observed in code: requires PyTorch for contrastive loss. (core/indicators/fractal_gcl.py:22-33, 47-60)

EVIDENCE:
- Functions: `fractal_boxcover`, `fd_one_shot`, `contrastive_loss_fractal`, `fractal_gcl_novelty`. (core/indicators/fractal_gcl.py:10-90)
- Constants/thresholds: default `max_box=4`, `tau=0.2`. (core/indicators/fractal_gcl.py:14-30, 47-60)
- Backend selection logic: optional `torch` availability. (core/indicators/fractal_gcl.py:12-24)
- Input validation: `max_box > 0`, embedding dimensionality checks. (core/indicators/fractal_gcl.py:14-30, 67-78)

MATH CONTRACT:
- **Definition:** Observed in code: FD via log–log slope; loss via log-softmax with temperature. (core/indicators/fractal_gcl.py:31-60)
- **Domain:** Observed in code: graph nodes, positive `max_box`, embeddings 2D. (core/indicators/fractal_gcl.py:14-30, 67-78)
- **Range:** Not in code; removed. (core/indicators/fractal_gcl.py:1-108)
- **Invariants:** Observed in code: embeddings normalized prior to cosine. (core/indicators/fractal_gcl.py:80-88)
- **Failure modes:** Observed in code: raises `ImportError` if torch missing for loss. (core/indicators/fractal_gcl.py:47-55)
- **Approximation notes:** PROXY: FD estimated by single log–log fit. (core/indicators/fractal_gcl.py:31-45)
- **Complexity:** Not in code; removed. (core/indicators/fractal_gcl.py:1-108)
- **Determinism:** Observed in code: deterministic given inputs. (core/indicators/fractal_gcl.py:10-90)

### Novelty scores (`core/indicators/novelty.py`)
- **Symbolic name:** Observed in code: KL divergence and cosine-based novelty. (core/indicators/novelty.py:1-20)
- **Code location(s):** `core/indicators/novelty.py`. (core/indicators/novelty.py:1-20)
- **Type:** Observed in code: deterministic. (core/indicators/novelty.py:1-20)
- **Inputs/outputs:** Observed in code: probability vectors and embeddings; outputs scalars. (core/indicators/novelty.py:4-20)
- **Implicit assumptions:** Observed in code: vectors normalized with clipping. (core/indicators/novelty.py:6-18)
- **Known or suspected weaknesses:** Observed in code: fixed clip `1e-8`. (core/indicators/novelty.py:6-12)

EVIDENCE:
- Functions: `kl_div`, `novelty_score`. (core/indicators/novelty.py:4-20)
- Constants/thresholds: clip `1e-8`. (core/indicators/novelty.py:6-12)
- Backend selection logic: none observed. (core/indicators/novelty.py:1-20)
- Input validation: none observed. (core/indicators/novelty.py:1-20)

MATH CONTRACT:
- **Definition:** Observed in code: KL divergence using clipped probabilities; novelty = 1 - cosine. (core/indicators/novelty.py:4-20)
- **Domain:** Not in code; removed. (core/indicators/novelty.py:1-20)
- **Range:** Not in code; removed. (core/indicators/novelty.py:1-20)
- **Invariants:** Observed in code: vectors normalized before cosine. (core/indicators/novelty.py:14-18)
- **Failure modes:** Not in code; removed. (core/indicators/novelty.py:1-20)
- **Approximation notes:** PROXY: clipping avoids log(0). (core/indicators/novelty.py:6-12)
- **Complexity:** Not in code; removed. (core/indicators/novelty.py:1-20)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/novelty.py:1-20)

### Trading indicator wrappers (`core/indicators/trading.py`)
- **Symbolic name:** Observed in code: Kuramoto \(R\), Hurst \(H\), VPIN. (core/indicators/trading.py:331-626)
- **Code location(s):** `core/indicators/trading.py`. (core/indicators/trading.py:1-630)
- **Type:** Observed in code: deterministic rolling estimators, optional GPU. (core/indicators/trading.py:331-626)
- **Inputs/outputs:** Observed in code: price/volume sequences; outputs rolling arrays. (core/indicators/trading.py:331-626)
- **Implicit assumptions:** Observed in code: window sizes and lengths validated, finite arrays expected. (core/indicators/trading.py:350-420, 470-540)
- **Known or suspected weaknesses:** Observed in code: GPU kernels optional. (core/indicators/trading.py:83-120)

EVIDENCE:
- Functions/classes: `KuramotoIndicator`, `HurstIndicator`, `VPINIndicator`. (core/indicators/trading.py:331-626)
- Constants/thresholds: default window sizes and parameters in dataclass defaults. (core/indicators/trading.py:331-560)
- Backend selection logic: GPU availability checks and CUDA kernel usage. (core/indicators/trading.py:83-120, 137-199)
- Input validation: window and array shape checks in compute methods. (core/indicators/trading.py:350-420, 470-540)

MATH CONTRACT:
- **Definition:** Observed in code: wrappers call underlying Kuramoto/Hurst/VPIN computations. (core/indicators/trading.py:364-626)
- **Domain:** Observed in code: numeric sequences; window size < length. (core/indicators/trading.py:350-420, 470-540)
- **Range:** Observed in code: Kuramoto and Hurst outputs rely on underlying bounded outputs. (core/indicators/trading.py:364-504; core/indicators/kuramoto.py:142-147; core/indicators/hurst.py:430-450)
- **Invariants:** Observed in code: ratios and saturation tracked as metrics. (core/indicators/trading.py:381-450, 577-626)
- **Failure modes:** Observed in code: invalid shapes or missing data raise exceptions or return zeros. (core/indicators/trading.py:350-420, 470-540)
- **Approximation notes:** Not in code; removed. (core/indicators/trading.py:1-630)
- **Complexity:** Not in code; removed. (core/indicators/trading.py:1-630)
- **Determinism:** Observed in code: no RNG usage. (core/indicators/trading.py:1-626)

---

## Neuro Subsystems (`core/neuro`)

### Adaptive Market Mind (AMM) (`core/neuro/amm.py`)
- **Symbolic name:** Observed in code: precision-weighted prediction error with homeostatic gain control. (core/neuro/amm.py:1-200)
- **Code location(s):** `core/neuro/amm.py`. (core/neuro/amm.py:1-220)
- **Type:** Observed in code: deterministic discrete-time state updates. (core/neuro/amm.py:110-190)
- **Inputs/outputs:** Observed in code: return observation, Kuramoto \(R\), Ricci \(\kappa\), optional entropy; outputs pulse and precision. (core/neuro/amm.py:120-190)
- **Implicit assumptions:** Observed in code: config parameters are positive and clipped; entropy uses fixed bins. (core/neuro/amm.py:42-70, 150-190)
- **Known or suspected weaknesses:** Observed in code: fixed clipping bounds `pi_min/pi_max`. (core/neuro/amm.py:62-70, 136-150)

EVIDENCE:
- Functions/classes: `AdaptiveMarketMind`, `AMMConfig`. (core/neuro/amm.py:41-190)
- Constants/thresholds: config defaults for decay, gains, and bounds. (core/neuro/amm.py:42-70)
- Backend selection logic: none observed. (core/neuro/amm.py:1-190)
- Input validation: none observed in constructor; values used directly. (core/neuro/amm.py:41-190)

MATH CONTRACT:
- **Definition:** Observed in code: EMA prediction, EW variance, precision \(\pi\) from variance/entropy/Kuramoto/Ricci, pulse from tanh and homeostasis. (core/neuro/amm.py:120-190)
- **Domain:** Not in code; removed. (core/neuro/amm.py:1-220)
- **Range:** Observed in code: precision clipped to `[pi_min, pi_max]`. (core/neuro/amm.py:136-150)
- **Invariants:** Observed in code: EW variance updated with epsilon. (core/neuro/amm.py:130-145)
- **Failure modes:** Not in code; removed. (core/neuro/amm.py:1-220)
- **Approximation notes:** PROXY: entropy uses fixed-bin EW histogram. (core/neuro/amm.py:70-90)
- **Complexity:** Observed in code: O(1) per update. (core/neuro/amm.py:1-30)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/amm.py:1-190)

### Streaming exponential-weighted features (`core/neuro/features.py`)
- **Symbolic name:** Observed in code: EMA, EW variance, EW entropy, EW momentum, EW z-score, EW skewness. (core/neuro/features.py:32-330)
- **Code location(s):** `core/neuro/features.py`. (core/neuro/features.py:1-348)
- **Type:** Observed in code: deterministic, O(1) streaming updates. (core/neuro/features.py:1-30, 83-330)
- **Inputs/outputs:** Observed in code: scalar updates; output scalar statistics. (core/neuro/features.py:39-330)
- **Implicit assumptions:** Observed in code: span/decay parameters validated in constructors. (core/neuro/features.py:109-200)
- **Known or suspected weaknesses:** Observed in code: entropy bins fixed by config bounds. (core/neuro/features.py:53-83)

EVIDENCE:
- Functions/classes: `ema_update`, `ewvar_update`, `EWEntropy`, `EWMomentum`, `EWZScore`, `EWSkewness`. (core/neuro/features.py:39-330)
- Constants/thresholds: entropy config defaults. (core/neuro/features.py:53-60)
- Backend selection logic: none observed. (core/neuro/features.py:1-330)
- Input validation: parameter validation in constructors. (core/neuro/features.py:109-200, 269-290)

MATH CONTRACT:
- **Definition:** Observed in code: EMA/variance recurrences and entropy from EW histogram counts. (core/neuro/features.py:39-90)
- **Domain:** Observed in code: spans positive; lambda in (0,1). (core/neuro/features.py:109-200)
- **Range:** Not in code; removed. (core/neuro/features.py:1-348)
- **Invariants:** Observed in code: histogram counts positive via prior. (core/neuro/features.py:66-82)
- **Failure modes:** Observed in code: invalid params raise `ValueError`. (core/neuro/features.py:120-200)
- **Approximation notes:** PROXY: entropy via fixed bins and EW decay. (core/neuro/features.py:53-83)
- **Complexity:** Observed in code: O(1) updates. (core/neuro/features.py:1-30)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/features.py:1-330)

### Streaming quantile estimation (`core/neuro/quantile.py`)
- **Symbolic name:** Observed in code: exact quantiles and P² algorithm. (core/neuro/quantile.py:1-220)
- **Code location(s):** `core/neuro/quantile.py`. (core/neuro/quantile.py:1-339)
- **Type:** Observed in code: deterministic estimators (exact and approximate). (core/neuro/quantile.py:48-320)
- **Inputs/outputs:** Observed in code: stream of finite scalars; outputs quantile estimate. (core/neuro/quantile.py:60-320)
- **Implicit assumptions:** Observed in code: quantile in (0,1); observations finite. (core/neuro/quantile.py:60-120, 163-210)
- **Known or suspected weaknesses:** Observed in code: P² algorithm is approximate. (core/neuro/quantile.py:146-170)

EVIDENCE:
- Functions/classes: `ExactQuantile`, `P2Algorithm`. (core/neuro/quantile.py:48-320)
- Constants/thresholds: initialization uses 5 markers. (core/neuro/quantile.py:146-200)
- Backend selection logic: none observed. (core/neuro/quantile.py:1-320)
- Input validation: quantile and finite observation checks. (core/neuro/quantile.py:60-120, 163-210)

MATH CONTRACT:
- **Definition:** Observed in code: exact order-statistic quantile; P² piecewise-parabolic updates. (core/neuro/quantile.py:48-210)
- **Domain:** Observed in code: q in (0,1), finite observations. (core/neuro/quantile.py:60-120, 163-210)
- **Range:** Not in code; removed. (core/neuro/quantile.py:1-339)
- **Invariants:** Observed in code: marker positions updated monotonically. (core/neuro/quantile.py:210-280)
- **Failure modes:** Observed in code: invalid inputs raise `ValueError`. (core/neuro/quantile.py:60-120, 163-210)
- **Approximation notes:** PROXY: P² is approximate by design. (core/neuro/quantile.py:146-170)
- **Complexity:** Observed in code: exact uses O(n) memory, P² uses O(1) memory. (core/neuro/quantile.py:1-40)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/quantile.py:1-320)

### Position sizing (`core/neuro/sizing.py`)
- **Symbolic name:** Observed in code: volatility-targeted sizing and Kelly sizing. (core/neuro/sizing.py:1-250)
- **Code location(s):** `core/neuro/sizing.py`. (core/neuro/sizing.py:1-310)
- **Type:** Observed in code: deterministic sizing formulas. (core/neuro/sizing.py:122-250)
- **Inputs/outputs:** Observed in code: direction, precision, pulse, volatility; outputs leverage or weights. (core/neuro/sizing.py:158-250)
- **Implicit assumptions:** Observed in code: configuration validated; volatility non-negative. (core/neuro/sizing.py:72-120, 172-190)
- **Known or suspected weaknesses:** Observed in code: logistic precision mapping uses log with safe minimum. (core/neuro/sizing.py:142-156)

EVIDENCE:
- Functions/classes: `SizerConfig`, `position_size`, `kelly_size`, `risk_parity_weight`. (core/neuro/sizing.py:45-280)
- Constants/thresholds: uses `LOG_SAFE_MIN`, `VOLATILITY_SAFE_MIN`, `POSITION_SIZE_MIN`. (core/neuro/sizing.py:32-40, 142-190)
- Backend selection logic: none observed. (core/neuro/sizing.py:1-280)
- Input validation: config validation and sigma checks. (core/neuro/sizing.py:72-120, 172-190)

MATH CONTRACT:
- **Definition:** Observed in code: size = direction * weight * (target_vol / est_sigma). (core/neuro/sizing.py:158-190)
- **Domain:** Observed in code: positive target volatility, non-negative sigma. (core/neuro/sizing.py:72-120, 172-190)
- **Range:** Observed in code: output clipped to \([-max_leverage, max_leverage]\). (core/neuro/sizing.py:190-199)
- **Invariants:** Observed in code: returns 0 if direction=0 or filters fail. (core/neuro/sizing.py:163-185)
- **Failure modes:** Observed in code: negative sigma raises `ValueError`. (core/neuro/sizing.py:172-176)
- **Approximation notes:** PROXY: precision mapping uses log-sigmoid. (core/neuro/sizing.py:142-156)
- **Complexity:** Not in code; removed. (core/neuro/sizing.py:1-310)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/sizing.py:1-250)

### Fractal analytics (`core/neuro/fractal.py`)
- **Symbolic name:** Observed in code: rescaled range, Hurst, fractal dimension, multiscale energy. (core/neuro/fractal.py:11-140)
- **Code location(s):** `core/neuro/fractal.py`. (core/neuro/fractal.py:1-171)
- **Type:** Observed in code: deterministic estimators. (core/neuro/fractal.py:11-140)
- **Inputs/outputs:** Observed in code: 1D series; outputs scalars and `FractalSummary`. (core/neuro/fractal.py:11-140)
- **Implicit assumptions:** Observed in code: input finite and non-empty. (core/neuro/fractal.py:19-28)
- **Known or suspected weaknesses:** Observed in code: uses fixed small epsilon via validation. (core/neuro/fractal.py:19-28)

EVIDENCE:
- Functions/classes: `rescaled_range`, `hurst_exponent`, `fractal_dimension_from_hurst`, `multiscale_energy`. (core/neuro/fractal.py:11-118)
- Constants/thresholds: none observed. (core/neuro/fractal.py:1-118)
- Backend selection logic: none observed. (core/neuro/fractal.py:1-118)
- Input validation: `_validate_series` finite checks. (core/neuro/fractal.py:19-28)

MATH CONTRACT:
- **Definition:** Observed in code: R/S computation and Hurst -> fractal dimension. (core/neuro/fractal.py:30-102)
- **Domain:** Observed in code: 1D finite series. (core/neuro/fractal.py:19-28)
- **Range:** Not in code; removed. (core/neuro/fractal.py:1-171)
- **Invariants:** Not in code; removed. (core/neuro/fractal.py:1-171)
- **Failure modes:** Observed in code: invalid series raises `ValueError`. (core/neuro/fractal.py:19-28)
- **Approximation notes:** PROXY: Hurst via rescaled range for finite windows. (core/neuro/fractal.py:30-70)
- **Complexity:** Not in code; removed. (core/neuro/fractal.py:1-171)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/fractal.py:1-118)

### Fractal regulator (`core/neuro/fractal_regulator.py`)
- **Symbolic name:** Observed in code: regulator metrics derived from fractal properties and energy. (core/neuro/fractal_regulator.py:17-308)
- **Code location(s):** `core/neuro/fractal_regulator.py`. (core/neuro/fractal_regulator.py:1-357)
- **Type:** Observed in code: deterministic, discrete-time controller. (core/neuro/fractal_regulator.py:58-308)
- **Inputs/outputs:** Observed in code: signal stream; outputs `RegulatorMetrics`. (core/neuro/fractal_regulator.py:58-308)
- **Implicit assumptions:** Observed in code: window sizes and buffers exist. (core/neuro/fractal_regulator.py:58-120)
- **Known or suspected weaknesses:** Observed in code: uses fixed thresholds in config. (core/neuro/fractal_regulator.py:58-120)

EVIDENCE:
- Functions/classes: `EEPFractalRegulator`, `RegulatorMetrics`. (core/neuro/fractal_regulator.py:25-308)
- Constants/thresholds: defaults in constructor. (core/neuro/fractal_regulator.py:58-120)
- Backend selection logic: none observed. (core/neuro/fractal_regulator.py:1-308)
- Input validation: none observed. (core/neuro/fractal_regulator.py:1-308)

MATH CONTRACT:
- **Definition:** Observed in code: computes Hurst, PLE, CSI, energy and efficiency metrics. (core/neuro/fractal_regulator.py:125-282)
- **Domain:** Not in code; removed. (core/neuro/fractal_regulator.py:1-357)
- **Range:** Not in code; removed. (core/neuro/fractal_regulator.py:1-357)
- **Invariants:** Observed in code: metrics only available after updates. (core/neuro/fractal_regulator.py:282-300)
- **Failure modes:** Not in code; removed. (core/neuro/fractal_regulator.py:1-357)
- **Approximation notes:** PROXY: estimator-based metrics. (core/neuro/fractal_regulator.py:125-230)
- **Complexity:** Not in code; removed. (core/neuro/fractal_regulator.py:1-357)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/fractal_regulator.py:1-308)

### ECS-inspired regulator (`core/neuro/ecs_regulator.py`)
- **Symbolic name:** Observed in code: risk threshold dynamics with bounded gradients and Lyapunov-style metrics. (core/neuro/ecs_regulator.py:1-520)
- **Code location(s):** `core/neuro/ecs_regulator.py`. (core/neuro/ecs_regulator.py:1-1133)
- **Type:** Observed in code: deterministic, discrete-time controller. (core/neuro/ecs_regulator.py:131-520)
- **Inputs/outputs:** Observed in code: stress series, volatility, predictions; outputs decisions and metrics. (core/neuro/ecs_regulator.py:515-800)
- **Implicit assumptions:** Observed in code: thresholds and multipliers validated in constructor. (core/neuro/ecs_regulator.py:131-220)
- **Known or suspected weaknesses:** Observed in code: fixed constants defined at module scope. (core/neuro/ecs_regulator.py:30-60)

EVIDENCE:
- Functions/classes: `ECSInspiredRegulator`, `ECSMetrics`, `StabilityMetrics`. (core/neuro/ecs_regulator.py:64-1085)
- Constants/thresholds: module constants like `GRADIENT_BOUND_MAX`, `FE_STABILITY_EPSILON`. (core/neuro/ecs_regulator.py:30-60)
- Backend selection logic: none observed. (core/neuro/ecs_regulator.py:1-520)
- Input validation: constructor checks. (core/neuro/ecs_regulator.py:131-220)

MATH CONTRACT:
- **Definition:** Observed in code: bounded gradient updates and conformal thresholds for decision gating. (core/neuro/ecs_regulator.py:255-520, 481-520)
- **Domain:** Observed in code: parameter bounds enforced in constructor. (core/neuro/ecs_regulator.py:131-220)
- **Range:** Observed in code: gradient clipping and threshold bounds. (core/neuro/ecs_regulator.py:255-360)
- **Invariants:** Observed in code: monotonic free-energy descent enforcement. (core/neuro/ecs_regulator.py:360-405)
- **Failure modes:** Observed in code: invalid parameters raise `ValueError`. (core/neuro/ecs_regulator.py:131-220)
- **Approximation notes:** PROXY: Kalman filter and conformal bounds are estimator-based. (core/neuro/ecs_regulator.py:744-769, 481-520)
- **Complexity:** Not in code; removed. (core/neuro/ecs_regulator.py:1-1133)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/ecs_regulator.py:1-800)

### Motivation and bandit logic (`core/neuro/motivation.py`)
- **Symbolic name:** Observed in code: softmax bandit, intrinsic reward, information gain. (core/neuro/motivation.py:22-455)
- **Code location(s):** `core/neuro/motivation.py`. (core/neuro/motivation.py:1-537)
- **Type:** Observed in code: deterministic given inputs. (core/neuro/motivation.py:22-455)
- **Inputs/outputs:** Observed in code: state vectors and rewards; outputs strategy decisions. (core/neuro/motivation.py:33-407)
- **Implicit assumptions:** Observed in code: inputs are numeric arrays; normalization in `_softmax`. (core/neuro/motivation.py:22-33)
- **Known or suspected weaknesses:** Observed in code: temperature/weights are fixed defaults. (core/neuro/motivation.py:299-340)

EVIDENCE:
- Functions/classes: `FractalBandit`, `FractalMotivationEngine`, `FractalMotivationController`. (core/neuro/motivation.py:33-455)
- Constants/thresholds: defaults in constructor args. (core/neuro/motivation.py:299-340)
- Backend selection logic: none observed. (core/neuro/motivation.py:1-455)
- Input validation: none observed. (core/neuro/motivation.py:1-455)

MATH CONTRACT:
- **Definition:** Observed in code: softmax-based selection and reward updates. (core/neuro/motivation.py:22-69)
- **Domain:** Not in code; removed. (core/neuro/motivation.py:1-537)
- **Range:** Not in code; removed. (core/neuro/motivation.py:1-537)
- **Invariants:** Observed in code: softmax normalizes to probability vector. (core/neuro/motivation.py:22-33)
- **Failure modes:** Not in code; removed. (core/neuro/motivation.py:1-537)
- **Approximation notes:** PROXY: softmax uses fixed temperature. (core/neuro/motivation.py:22-33)
- **Complexity:** Not in code; removed. (core/neuro/motivation.py:1-537)
- **Determinism:** Observed in code: no RNG usage. (core/neuro/motivation.py:1-455)

### Shock scenario generator (`core/neuro/shocks.py`)
- **Symbolic name:** Observed in code: stochastic shock policy using normal distribution. (core/neuro/shocks.py:23-120)
- **Code location(s):** `core/neuro/shocks.py`. (core/neuro/shocks.py:1-245)
- **Type:** Observed in code: stochastic (uses random sampling from policy). (core/neuro/shocks.py:46-220)
- **Inputs/outputs:** Observed in code: feature dimension and training steps; outputs shock scenarios. (core/neuro/shocks.py:73-220)
- **Implicit assumptions:** Observed in code: PyTorch availability for learned policy. (core/neuro/shocks.py:40-70)
- **Known or suspected weaknesses:** Observed in code: fallback class when torch missing. (core/neuro/shocks.py:63-70)

EVIDENCE:
- Functions/classes: `ShockScenarioGenerator`, `_ShockPolicy`, `ShockScenario`. (core/neuro/shocks.py:23-220)
- Constants/thresholds: training steps and batch size defaults. (core/neuro/shocks.py:73-90)
- Backend selection logic: torch optional import. (core/neuro/shocks.py:40-70)
- Input validation: none observed. (core/neuro/shocks.py:1-220)

MATH CONTRACT:
- **Definition:** Observed in code: policy outputs `Normal` distribution for shocks. (core/neuro/shocks.py:46-60)
- **Domain:** Not in code; removed. (core/neuro/shocks.py:1-245)
- **Range:** Not in code; removed. (core/neuro/shocks.py:1-245)
- **Invariants:** Not in code; removed. (core/neuro/shocks.py:1-245)
- **Failure modes:** Observed in code: `ImportError` if torch missing for training path. (core/neuro/shocks.py:40-70)
- **Approximation notes:** PROXY: learned policy approximates shock distribution. (core/neuro/shocks.py:46-120)
- **Complexity:** Not in code; removed. (core/neuro/shocks.py:1-245)
- **Determinism:** Observed in code: sampling from distributions implies stochasticity. (core/neuro/shocks.py:46-120)

### Calibration (random search) (`core/neuro/calibration.py`)
- **Symbolic name:** Observed in code: random search over AMM config space. (core/neuro/calibration.py:67-140)
- **Code location(s):** `core/neuro/calibration.py`. (core/neuro/calibration.py:1-170)
- **Type:** Observed in code: stochastic optimization via random sampling. (core/neuro/calibration.py:67-140)
- **Inputs/outputs:** Observed in code: parameter ranges and evaluation function; outputs best config and score. (core/neuro/calibration.py:67-140)
- **Implicit assumptions:** Observed in code: random draws via `np.random`. (core/neuro/calibration.py:67-90)
- **Known or suspected weaknesses:** Observed in code: no gradient information. (core/neuro/calibration.py:67-140)

EVIDENCE:
- Functions/classes: `calibrate_random`, `CalibConfig`, `CalibResult`. (core/neuro/calibration.py:33-140)
- Constants/thresholds: defaults in `CalibConfig`. (core/neuro/calibration.py:43-60)
- Backend selection logic: none observed. (core/neuro/calibration.py:1-140)
- Input validation: none observed. (core/neuro/calibration.py:1-140)

MATH CONTRACT:
- **Definition:** Observed in code: random sampling over parameter ranges with evaluation scoring. (core/neuro/calibration.py:67-140)
- **Domain:** Not in code; removed. (core/neuro/calibration.py:1-170)
- **Range:** Not in code; removed. (core/neuro/calibration.py:1-170)
- **Invariants:** Not in code; removed. (core/neuro/calibration.py:1-170)
- **Failure modes:** Not in code; removed. (core/neuro/calibration.py:1-170)
- **Approximation notes:** PROXY: stochastic search approximates optimum. (core/neuro/calibration.py:67-140)
- **Complexity:** Not in code; removed. (core/neuro/calibration.py:1-170)
- **Determinism:** Observed in code: uses RNG; results depend on random seed. (core/neuro/calibration.py:67-90)

---

## Execution Risk (`execution/risk`)

### Execution risk limits + kill-switch (`execution/risk/core.py`)
- **Symbolic name:** Observed in code: constraint enforcement on notional/position/order rates and drawdown. (execution/risk/core.py:55-140)
- **Code location(s):** `execution/risk/core.py`. (execution/risk/core.py:1-1530)
- **Type:** Observed in code: deterministic enforcement of limits. (execution/risk/core.py:55-360)
- **Inputs/outputs:** Observed in code: positions, notionals, rates; outputs violations and kill-switch state. (execution/risk/core.py:55-360)
- **Implicit assumptions:** Observed in code: limits normalized and clamped in `RiskLimits.__post_init__`. (execution/risk/core.py:90-140)
- **Known or suspected weaknesses:** Observed in code: uses fixed default multipliers for kill-switch. (execution/risk/core.py:79-120)

EVIDENCE:
- Functions/classes: `RiskLimits`, `RiskManager` (later in file). (execution/risk/core.py:55-140, 360-1200)
- Constants/thresholds: default limits in `RiskLimits`. (execution/risk/core.py:79-120)
- Backend selection logic: none observed. (execution/risk/core.py:1-360)
- Input validation: normalization in `RiskLimits.__post_init__`. (execution/risk/core.py:90-140)

MATH CONTRACT:
- **Definition:** Observed in code: apply limit checks and kill-switch escalation logic. (execution/risk/core.py:360-720)
- **Domain:** Observed in code: limits normalized to non-negative; drawdown in (0,1]. (execution/risk/core.py:90-140)
- **Range:** Not in code; removed. (execution/risk/core.py:1-1530)
- **Invariants:** Observed in code: kill-switch state persisted and validated. (execution/risk/core.py:120-240)
- **Failure modes:** Observed in code: invalid drawdown raises `ValueError`. (execution/risk/core.py:110-140)
- **Approximation notes:** Not in code; removed. (execution/risk/core.py:1-1530)
- **Complexity:** Not in code; removed. (execution/risk/core.py:1-1530)
- **Determinism:** Observed in code: no RNG usage. (execution/risk/core.py:1-720)

---

## GeoSync Core Neuro (`src/geosync/core/neuro`)

### Dopamine controller + action gate (`src/geosync/core/neuro/dopamine/dopamine_controller.py`)
- **Symbolic name:** Observed in code: TD(0) reward prediction error, logistic gating, DDM-derived thresholds. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-400; src/geosync/core/neuro/dopamine/action_gate.py:1-120; src/geosync/core/neuro/dopamine/ddm_adapter.py:1-112)
- **Code location(s):** `dopamine_controller.py`, `action_gate.py`, `ddm_adapter.py`. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-1441; src/geosync/core/neuro/dopamine/action_gate.py:1-151; src/geosync/core/neuro/dopamine/ddm_adapter.py:1-112)
- **Type:** Observed in code: deterministic controller with configurable parameters. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-400)
- **Inputs/outputs:** Observed in code: rewards, novelty, thresholds; outputs gating decision and temperature. (src/geosync/core/neuro/dopamine/action_gate.py:25-140)
- **Implicit assumptions:** Observed in code: monotonic thresholds validated; parameters clamped. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-200; src/geosync/core/neuro/dopamine/_invariants.py:1-200 if present)
- **Known or suspected weaknesses:** Observed in code: logistic input clipping bounds. (src/geosync/core/neuro/dopamine/dopamine_controller.py:34-120)

EVIDENCE:
- Functions/classes: `DopamineConfig`, `DopamineController`, `ActionGate`, `DDMThresholds`, `ddm_thresholds`. (src/geosync/core/neuro/dopamine/dopamine_controller.py:34-300; src/geosync/core/neuro/dopamine/action_gate.py:15-140; src/geosync/core/neuro/dopamine/ddm_adapter.py:1-112)
- Constants/thresholds: `logistic_clip_min/max`, gate thresholds in config. (src/geosync/core/neuro/dopamine/dopamine_controller.py:34-120)
- Backend selection logic: none observed. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-300)
- Input validation: config validation and threshold checks. (src/geosync/core/neuro/dopamine/dopamine_controller.py:200-320)

MATH CONTRACT:
- **Definition:** Observed in code: TD(0) RPE and logistic gating thresholds. (src/geosync/core/neuro/dopamine/dopamine_controller.py:400-620; src/geosync/core/neuro/dopamine/action_gate.py:80-120)
- **Domain:** Observed in code: configuration bounds and monotonic thresholds. (src/geosync/core/neuro/dopamine/dopamine_controller.py:200-320)
- **Range:** Observed in code: gate outputs in bounded ranges and temperature clipped. (src/geosync/core/neuro/dopamine/action_gate.py:80-120; src/geosync/core/neuro/dopamine/dopamine_controller.py:500-620)
- **Invariants:** Observed in code: monotonic threshold enforcement. (src/geosync/core/neuro/dopamine/_invariants.py:1-120)
- **Failure modes:** Observed in code: invalid configs raise `ValueError`. (src/geosync/core/neuro/dopamine/dopamine_controller.py:200-320)
- **Approximation notes:** PROXY: DDM thresholds are heuristic adapter to gate parameters. (src/geosync/core/neuro/dopamine/ddm_adapter.py:1-112)
- **Complexity:** Not in code; removed. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-1441)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/core/neuro/dopamine/dopamine_controller.py:1-620)

### GABA inhibition gate (`src/geosync/core/neuro/gaba/gaba_inhibition_gate.py`)
- **Symbolic name:** Observed in code: inhibition coefficient from impulse trace and STDP-like plasticity. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:1-220)
- **Code location(s):** `src/geosync/core/neuro/gaba/gaba_inhibition_gate.py`. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:1-273)
- **Type:** Observed in code: deterministic, discrete-time controller. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:120-240)
- **Inputs/outputs:** Observed in code: impulse, stress, RPE; outputs inhibition. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:200-260)
- **Implicit assumptions:** Observed in code: configuration validation via `ensure_float`. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:132-190)
- **Known or suspected weaknesses:** Observed in code: fixed max inhibition (<=0.99). (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:156-170)

EVIDENCE:
- Functions/classes: `GABAConfig`, `GABAInhibitionGate`. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:38-240)
- Constants/thresholds: config defaults via YAML; bounds in validation. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:132-190)
- Backend selection logic: none observed. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:1-240)
- Input validation: `_validate_config` ensures bounds. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:132-190)

MATH CONTRACT:
- **Definition:** Observed in code: inhibition derived from impulse trace and RPE with optional plasticity. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:200-260)
- **Domain:** Observed in code: config bounds for decay and thresholds. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:132-190)
- **Range:** Observed in code: inhibition is clamped to [0, max_inhibition]. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:200-260)
- **Invariants:** Observed in code: traces are non-negative after sanitization. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:38-70, 200-240)
- **Failure modes:** Observed in code: missing config keys raise `ValueError`. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:132-144)
- **Approximation notes:** PROXY: STDP-like updates are heuristic rules. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:200-240)
- **Complexity:** Not in code; removed. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:1-273)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/core/neuro/gaba/gaba_inhibition_gate.py:1-240)

### NA/ACh neuromodulator (`src/geosync/core/neuro/na_ach/neuromods.py`)
- **Symbolic name:** Observed in code: arousal/attention update with linear gains and clamping. (src/geosync/core/neuro/na_ach/neuromods.py:1-180)
- **Code location(s):** `src/geosync/core/neuro/na_ach/neuromods.py`. (src/geosync/core/neuro/na_ach/neuromods.py:1-214)
- **Type:** Observed in code: deterministic, discrete-time. (src/geosync/core/neuro/na_ach/neuromods.py:120-200)
- **Inputs/outputs:** Observed in code: volatility and novelty inputs; outputs arousal/attention and risk/temperature scales. (src/geosync/core/neuro/na_ach/neuromods.py:120-200)
- **Implicit assumptions:** Observed in code: config bounds enforced. (src/geosync/core/neuro/na_ach/neuromods.py:82-140)
- **Known or suspected weaknesses:** Observed in code: clamping to fixed ranges (risk_min/max, attention min/max). (src/geosync/core/neuro/na_ach/neuromods.py:82-140)

EVIDENCE:
- Functions/classes: `NAACHConfig`, `NAACHNeuromodulator`. (src/geosync/core/neuro/na_ach/neuromods.py:17-200)
- Constants/thresholds: config bounds via `ensure_float`. (src/geosync/core/neuro/na_ach/neuromods.py:82-140)
- Backend selection logic: none observed. (src/geosync/core/neuro/na_ach/neuromods.py:1-200)
- Input validation: `_validate_config`. (src/geosync/core/neuro/na_ach/neuromods.py:82-140)

MATH CONTRACT:
- **Definition:** Observed in code: linear gain update of arousal/attention, clamped. (src/geosync/core/neuro/na_ach/neuromods.py:150-200)
- **Domain:** Observed in code: non-negative inputs after clamping. (src/geosync/core/neuro/na_ach/neuromods.py:150-160)
- **Range:** Observed in code: risk multiplier and temperature scale clamped. (src/geosync/core/neuro/na_ach/neuromods.py:170-190)
- **Invariants:** Observed in code: arousal/attention remain within min/max. (src/geosync/core/neuro/na_ach/neuromods.py:150-180)
- **Failure modes:** Observed in code: missing config keys raise `ValueError`. (src/geosync/core/neuro/na_ach/neuromods.py:82-100)
- **Approximation notes:** PROXY: linear gain model. (src/geosync/core/neuro/na_ach/neuromods.py:150-180)
- **Complexity:** Not in code; removed. (src/geosync/core/neuro/na_ach/neuromods.py:1-214)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/core/neuro/na_ach/neuromods.py:1-200)

### Serotonin controller (`src/geosync/core/neuro/serotonin/serotonin_controller.py`)
- **Symbolic name:** Observed in code: logistic inhibition with tonic/phasic components and desensitization. (src/geosync/core/neuro/serotonin/serotonin_controller.py:1-240)
- **Code location(s):** `src/geosync/core/neuro/serotonin/serotonin_controller.py`. (src/geosync/core/neuro/serotonin/serotonin_controller.py:1-2038)
- **Type:** Observed in code: deterministic controller with persistent state. (src/geosync/core/neuro/serotonin/serotonin_controller.py:240-900)
- **Inputs/outputs:** Observed in code: volatility, free energy, losses; outputs hold/veto and inhibition level. (src/geosync/core/neuro/serotonin/serotonin_controller.py:900-1200)
- **Implicit assumptions:** Observed in code: config bounds validated via Pydantic. (src/geosync/core/neuro/serotonin/serotonin_controller.py:100-220)
- **Known or suspected weaknesses:** Observed in code: many fixed thresholds in config. (src/geosync/core/neuro/serotonin/serotonin_controller.py:120-220)

EVIDENCE:
- Functions/classes: `SerotoninConfig`, `SerotoninController`, `SerotoninStepResult`. (src/geosync/core/neuro/serotonin/serotonin_controller.py:100-1200)
- Constants/thresholds: config defaults and bounds. (src/geosync/core/neuro/serotonin/serotonin_controller.py:120-220)
- Backend selection logic: none observed. (src/geosync/core/neuro/serotonin/serotonin_controller.py:1-1200)
- Input validation: Pydantic field constraints. (src/geosync/core/neuro/serotonin/serotonin_controller.py:120-220)

MATH CONTRACT:
- **Definition:** Observed in code: logistic mapping from risk signals to inhibition, with phasic bursts and desensitization. (src/geosync/core/neuro/serotonin/serotonin_controller.py:900-1200)
- **Domain:** Observed in code: validated parameter bounds. (src/geosync/core/neuro/serotonin/serotonin_controller.py:120-220)
- **Range:** Observed in code: gating outputs are clamped in `gate_action`. (src/geosync/core/neuro/serotonin/serotonin_controller.py:1200-1400)
- **Invariants:** Observed in code: state updates guarded by locks. (src/geosync/core/neuro/serotonin/serotonin_controller.py:400-520)
- **Failure modes:** Observed in code: invalid config raises `ValidationError`. (src/geosync/core/neuro/serotonin/serotonin_controller.py:100-220)
- **Approximation notes:** PROXY: logistic gating and desensitization heuristics. (src/geosync/core/neuro/serotonin/serotonin_controller.py:900-1200)
- **Complexity:** Not in code; removed. (src/geosync/core/neuro/serotonin/serotonin_controller.py:1-2038)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/core/neuro/serotonin/serotonin_controller.py:1-1400)

### NaK controller (`src/geosync/core/neuro/nak/controller.py`)
- **Symbolic name:** Observed in code: softsign PI control with gating under drawdown/volatility. (src/geosync/core/neuro/nak/controller.py:1-160)
- **Code location(s):** `src/geosync/core/neuro/nak/controller.py`. (src/geosync/core/neuro/nak/controller.py:1-177)
- **Type:** Observed in code: deterministic, discrete-time controller. (src/geosync/core/neuro/nak/controller.py:30-160)
- **Inputs/outputs:** Observed in code: performance proxy, volatility, drawdown, features; outputs `r_final` and log. (src/geosync/core/neuro/nak/controller.py:45-160)
- **Implicit assumptions:** Observed in code: drawdown clamped to >= -1.0. (src/geosync/core/neuro/nak/controller.py:70-85)
- **Known or suspected weaknesses:** Observed in code: fixed thresholds and gains in config. (src/geosync/core/neuro/nak/controller.py:24-44)

EVIDENCE:
- Functions/classes: `NaKControllerV4_2`, `NaKConfig`. (src/geosync/core/neuro/nak/controller.py:17-160)
- Constants/thresholds: defaults in `NaKConfig`. (src/geosync/core/neuro/nak/controller.py:24-44)
- Backend selection logic: none observed. (src/geosync/core/neuro/nak/controller.py:1-160)
- Input validation: none observed. (src/geosync/core/neuro/nak/controller.py:1-160)

MATH CONTRACT:
- **Definition:** Observed in code: PI control on error with gating and desensitization multiplier. (src/geosync/core/neuro/nak/controller.py:90-150)
- **Domain:** Observed in code: drawdown clamped and volatility used in log1p. (src/geosync/core/neuro/nak/controller.py:70-120)
- **Range:** Observed in code: gate clamped to `[min_gate, 1.0]`. (src/geosync/core/neuro/nak/controller.py:120-140)
- **Invariants:** Observed in code: `E` clamped to `[0, E_max]`. (src/geosync/core/neuro/nak/controller.py:102-110)
- **Failure modes:** Not in code; removed. (src/geosync/core/neuro/nak/controller.py:1-177)
- **Approximation notes:** PROXY: heuristic gating thresholds. (src/geosync/core/neuro/nak/controller.py:24-44, 120-150)
- **Complexity:** Not in code; removed. (src/geosync/core/neuro/nak/controller.py:1-177)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/core/neuro/nak/controller.py:1-160)

---

## GeoSync Features (`src/geosync/features`)

### Kuramoto synchrony adapter (`src/geosync/features/kuramoto.py`)
- **Symbolic name:** Observed in code: Kuramoto order parameter \(R\) and \(\Delta R\). (src/geosync/features/kuramoto.py:90-160)
- **Code location(s):** `src/geosync/features/kuramoto.py`. (src/geosync/features/kuramoto.py:1-180)
- **Type:** Observed in code: deterministic. (src/geosync/features/kuramoto.py:60-160)
- **Inputs/outputs:** Observed in code: price DataFrame; outputs series for R, delta_R, labels. (src/geosync/features/kuramoto.py:70-160)
- **Implicit assumptions:** Observed in code: `DatetimeIndex` required; window length must be <= data length. (src/geosync/features/kuramoto.py:82-100)
- **Known or suspected weaknesses:** Observed in code: PROXY phase computed via arctan of rolling stats (simplified). (src/geosync/features/kuramoto.py:110-136)

EVIDENCE:
- Functions/classes: `KuramotoSynchrony`, `KuramotoResult`. (src/geosync/features/kuramoto.py:17-160)
- Constants/thresholds: default thresholds in constructor. (src/geosync/features/kuramoto.py:36-66)
- Backend selection logic: none observed. (src/geosync/features/kuramoto.py:1-160)
- Input validation: `DatetimeIndex` and length check. (src/geosync/features/kuramoto.py:82-100)

MATH CONTRACT:
- **Definition:** Observed in code: compute phases, \(R\), \(\Delta R\), label via rolling thresholds. (src/geosync/features/kuramoto.py:104-160)
- **Domain:** Observed in code: DatetimeIndex and sufficient length. (src/geosync/features/kuramoto.py:82-100)
- **Range:** Observed in code: \(R\) is magnitude of mean complex phase. (src/geosync/features/kuramoto.py:122-140)
- **Invariants:** Observed in code: labels always assigned for each timestamp. (src/geosync/features/kuramoto.py:142-160)
- **Failure modes:** Observed in code: invalid index/length raises `ValueError`. (src/geosync/features/kuramoto.py:82-100)
- **Approximation notes:** PROXY: phase computation via rolling mean/std rather than Hilbert transform. (src/geosync/features/kuramoto.py:110-136)
- **Complexity:** Not in code; removed. (src/geosync/features/kuramoto.py:1-180)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/features/kuramoto.py:1-160)

### Ricci curvature adapter (`src/geosync/features/ricci.py`)
- **Symbolic name:** Observed in code: approximate Ollivier–Ricci curvature on correlation graph. (src/geosync/features/ricci.py:1-200)
- **Code location(s):** `src/geosync/features/ricci.py`. (src/geosync/features/ricci.py:1-215)
- **Type:** Observed in code: deterministic. (src/geosync/features/ricci.py:60-200)
- **Inputs/outputs:** Observed in code: returns DataFrame; outputs edge curvatures and min curvature. (src/geosync/features/ricci.py:60-140)
- **Implicit assumptions:** Observed in code: uses correlation threshold and absolute correlation weights. (src/geosync/features/ricci.py:90-140)
- **Known or suspected weaknesses:** Observed in code: PROXY Wasserstein distance approximation via shortest paths. (src/geosync/features/ricci.py:120-200)

EVIDENCE:
- Functions/classes: `RicciCurvatureGraph`, `RicciResult`. (src/geosync/features/ricci.py:17-200)
- Constants/thresholds: defaults for `correlation_threshold`, `window`, `alpha`. (src/geosync/features/ricci.py:32-60)
- Backend selection logic: none observed. (src/geosync/features/ricci.py:1-200)
- Input validation: length check. (src/geosync/features/ricci.py:60-80)

MATH CONTRACT:
- **Definition:** Observed in code: \(\kappa=1-W/d\) on correlation graph edges. (src/geosync/features/ricci.py:120-200)
- **Domain:** Observed in code: requires sufficient window length. (src/geosync/features/ricci.py:60-80)
- **Range:** Not in code; removed. (src/geosync/features/ricci.py:1-215)
- **Invariants:** Observed in code: returns 0.0 when graph has no edges. (src/geosync/features/ricci.py:90-110)
- **Failure modes:** Observed in code: insufficient data raises `ValueError`. (src/geosync/features/ricci.py:60-80)
- **Approximation notes:** PROXY: simplified Wasserstein approximation. (src/geosync/features/ricci.py:120-200)
- **Complexity:** Not in code; removed. (src/geosync/features/ricci.py:1-215)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/features/ricci.py:1-200)

### Topological sentinel (`src/geosync/features/topo.py`)
- **Symbolic name:** Observed in code: topological score from persistent homology or proxy metrics. (src/geosync/features/topo.py:1-200)
- **Code location(s):** `src/geosync/features/topo.py`. (src/geosync/features/topo.py:1-247)
- **Type:** Observed in code: deterministic. (src/geosync/features/topo.py:60-220)
- **Inputs/outputs:** Observed in code: returns DataFrame; outputs `topo_score`. (src/geosync/features/topo.py:60-220)
- **Implicit assumptions:** Observed in code: requires at least two assets with variance. (src/geosync/features/topo.py:70-120)
- **Known or suspected weaknesses:** Observed in code: PROXY path used when `gudhi` unavailable. (src/geosync/features/topo.py:17-40, 146-200)

EVIDENCE:
- Functions/classes: `TopoSentinel`, `TopoResult`. (src/geosync/features/topo.py:17-220)
- Constants/thresholds: `persistence_threshold` default. (src/geosync/features/topo.py:36-50)
- Backend selection logic: optional `gudhi` import. (src/geosync/features/topo.py:17-30)
- Input validation: numeric column checks, window length checks. (src/geosync/features/topo.py:60-120)

MATH CONTRACT:
- **Definition:** Observed in code: persistent homology score or proxy eigenvalue-based score. (src/geosync/features/topo.py:120-200)
- **Domain:** Observed in code: numeric returns with sufficient assets and variance. (src/geosync/features/topo.py:70-120)
- **Range:** Not in code; removed. (src/geosync/features/topo.py:1-247)
- **Invariants:** Observed in code: returns 0.0 when data insufficient. (src/geosync/features/topo.py:70-120)
- **Failure modes:** Observed in code: missing gudhi triggers proxy path. (src/geosync/features/topo.py:17-40)
- **Approximation notes:** PROXY: eigenvalue/clustering proxy when gudhi missing. (src/geosync/features/topo.py:146-220)
- **Complexity:** Not in code; removed. (src/geosync/features/topo.py:1-247)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/features/topo.py:1-220)

### Causal guard (`src/geosync/features/causal.py`)
- **Symbolic name:** Observed in code: transfer entropy via histogram discretization. (src/geosync/features/causal.py:1-200)
- **Code location(s):** `src/geosync/features/causal.py`. (src/geosync/features/causal.py:1-245)
- **Type:** Observed in code: deterministic with optional Granger test. (src/geosync/features/causal.py:30-200)
- **Inputs/outputs:** Observed in code: DataFrame with target and drivers; outputs `TE_pass`. (src/geosync/features/causal.py:52-120)
- **Implicit assumptions:** Observed in code: target is numeric; sufficient length. (src/geosync/features/causal.py:60-100)
- **Known or suspected weaknesses:** Observed in code: PROXY histogram discretization; optional Granger if statsmodels available. (src/geosync/features/causal.py:120-200)

EVIDENCE:
- Functions/classes: `CausalGuard`, `CausalResult`. (src/geosync/features/causal.py:30-200)
- Constants/thresholds: defaults for `max_lag`, `n_bins`, `te_threshold`, `granger_alpha`. (src/geosync/features/causal.py:36-50)
- Backend selection logic: optional statsmodels import. (src/geosync/features/causal.py:20-30)
- Input validation: checks on target column and numeric dtype. (src/geosync/features/causal.py:60-100)

MATH CONTRACT:
- **Definition:** Observed in code: transfer entropy via conditional entropy differences. (src/geosync/features/causal.py:120-200)
- **Domain:** Observed in code: numeric target and sufficient length. (src/geosync/features/causal.py:60-100)
- **Range:** Observed in code: TE is non-negative (clamped). (src/geosync/features/causal.py:140-160)
- **Invariants:** Observed in code: returns `TE_pass=False` when insufficient data. (src/geosync/features/causal.py:70-90)
- **Failure modes:** Observed in code: missing target raises `ValueError`. (src/geosync/features/causal.py:60-70)
- **Approximation notes:** PROXY: histogram discretization and optional Granger confirmation. (src/geosync/features/causal.py:120-200)
- **Complexity:** Not in code; removed. (src/geosync/features/causal.py:1-245)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/features/causal.py:1-200)

---

## GeoSync Risk and Regime

### Risk homeostasis (`src/geosync/risk/risk_core.py`)
- **Symbolic name:** Observed in code: VaR/ES on losses; Kelly fraction \(f=\mu/\sigma^2\). (src/geosync/risk/risk_core.py:44-140)
- **Code location(s):** `src/geosync/risk/risk_core.py`. (src/geosync/risk/risk_core.py:1-185)
- **Type:** Observed in code: deterministic. (src/geosync/risk/risk_core.py:44-170)
- **Inputs/outputs:** Observed in code: returns array and parameters; outputs VaR/ES and sizing fractions. (src/geosync/risk/risk_core.py:44-170)
- **Implicit assumptions:** Observed in code: returns finite (filtered). (src/geosync/risk/risk_core.py:44-80)
- **Known or suspected weaknesses:** Observed in code: regime multipliers fixed in `kelly_shrink`. (src/geosync/risk/risk_core.py:86-120)

EVIDENCE:
- Functions/classes: `var_es`, `kelly_shrink`, `compute_final_size`, `check_risk_breach`, `RiskConfig`. (src/geosync/risk/risk_core.py:8-170)
- Constants/thresholds: env defaults `TP_ES_LIMIT`, `TP_VAR_ALPHA`, `TP_FMAX`. (src/geosync/risk/risk_core.py:20-40)
- Backend selection logic: none observed. (src/geosync/risk/risk_core.py:1-170)
- Input validation: finite filtering and sigma checks. (src/geosync/risk/risk_core.py:44-80, 86-100)

MATH CONTRACT:
- **Definition:** Observed in code: VaR via quantile of losses, ES via tail mean; Kelly shrinkage by regime. (src/geosync/risk/risk_core.py:44-140)
- **Domain:** Observed in code: finite returns; sigma2 > 0 for Kelly. (src/geosync/risk/risk_core.py:44-100)
- **Range:** Observed in code: returns 0.0 for empty inputs; sizes clipped to [0, f_max]. (src/geosync/risk/risk_core.py:52-80, 140-170)
- **Invariants:** Observed in code: ES >= VaR when tail exists. (src/geosync/risk/risk_core.py:60-80)
- **Failure modes:** Observed in code: non-finite ES triggers breach. (src/geosync/risk/risk_core.py:170-180)
- **Approximation notes:** Not in code; removed. (src/geosync/risk/risk_core.py:1-185)
- **Complexity:** Not in code; removed. (src/geosync/risk/risk_core.py:1-185)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/risk/risk_core.py:1-170)

### Automated risk testing (`src/geosync/risk/automated_testing.py`)
- **Symbolic name:** Observed in code: stress tests, Monte Carlo simulation, max drawdown, Sharpe ratio. (src/geosync/risk/automated_testing.py:170-723)
- **Code location(s):** `src/geosync/risk/automated_testing.py`. (src/geosync/risk/automated_testing.py:1-723)
- **Type:** Observed in code: deterministic metrics and stochastic Monte Carlo. (src/geosync/risk/automated_testing.py:295-360)
- **Inputs/outputs:** Observed in code: return arrays; outputs metrics and scenario results. (src/geosync/risk/automated_testing.py:210-360)
- **Implicit assumptions:** Observed in code: Monte Carlo draws normal distribution from mean/vol. (src/geosync/risk/automated_testing.py:295-340)
- **Known or suspected weaknesses:** Observed in code: scenario parameters are fixed in generators. (src/geosync/risk/automated_testing.py:440-576)

EVIDENCE:
- Functions/classes: `AutomatedRiskTester`, `validate_risk_metrics`, `_calculate_max_drawdown`, `_calculate_sharpe_ratio`. (src/geosync/risk/automated_testing.py:182-723)
- Constants/thresholds: scenario generator defaults. (src/geosync/risk/automated_testing.py:440-576)
- Backend selection logic: none observed. (src/geosync/risk/automated_testing.py:1-360)
- Input validation: parameter checks in constructors and `validate_risk_metrics`. (src/geosync/risk/automated_testing.py:182-240, 631-700)

MATH CONTRACT:
- **Definition:** Observed in code: drawdown and Sharpe formulas, Monte Carlo sampling from normal distribution. (src/geosync/risk/automated_testing.py:295-440)
- **Domain:** Observed in code: finite return arrays. (src/geosync/risk/automated_testing.py:420-440)
- **Range:** Not in code; removed. (src/geosync/risk/automated_testing.py:1-723)
- **Invariants:** Observed in code: risk breach determined by ES limit. (src/geosync/risk/automated_testing.py:233-255)
- **Failure modes:** Observed in code: insufficient data yields warnings. (src/geosync/risk/automated_testing.py:420-440)
- **Approximation notes:** PROXY: Monte Carlo uses normal distribution assumption. (src/geosync/risk/automated_testing.py:295-340)
- **Complexity:** Not in code; removed. (src/geosync/risk/automated_testing.py:1-723)
- **Determinism:** Observed in code: Monte Carlo sampling uses RNG. (src/geosync/risk/automated_testing.py:295-340)

### Early Warning System (`src/geosync/regime/ews.py`)
- **Symbolic name:** Observed in code: regime classification based on \(R, \Delta R, \kappa_{min}\), topo score, TE flag. (src/geosync/regime/ews.py:1-160)
- **Code location(s):** `src/geosync/regime/ews.py`. (src/geosync/regime/ews.py:1-215)
- **Type:** Observed in code: deterministic rule-based classifier. (src/geosync/regime/ews.py:60-200)
- **Inputs/outputs:** Observed in code: scalar metrics; outputs state and confidence. (src/geosync/regime/ews.py:60-200)
- **Implicit assumptions:** Observed in code: thresholds loaded from env/defaults. (src/geosync/regime/ews.py:20-52)
- **Known or suspected weaknesses:** Observed in code: threshold logic (PROXY). (src/geosync/regime/ews.py:60-200)

EVIDENCE:
- Functions/classes: `EWSAggregator`, `EWSConfig`, `EWSResult`. (src/geosync/regime/ews.py:12-200)
- Constants/thresholds: defaults in `EWSConfig`. (src/geosync/regime/ews.py:20-52)
- Backend selection logic: none observed. (src/geosync/regime/ews.py:1-200)
- Input validation: none observed. (src/geosync/regime/ews.py:1-200)

MATH CONTRACT:
- **Definition:** Observed in code: rule-based state selection with confidence. (src/geosync/regime/ews.py:60-200)
- **Domain:** Not in code; removed. (src/geosync/regime/ews.py:1-215)
- **Range:** Observed in code: confidence in [0,1] via averaging and thresholds. (src/geosync/regime/ews.py:120-200)
- **Invariants:** Observed in code: any kill condition triggers KILL. (src/geosync/regime/ews.py:88-120)
- **Failure modes:** Not in code; removed. (src/geosync/regime/ews.py:1-215)
- **Approximation notes:** PROXY: threshold logic. (src/geosync/regime/ews.py:60-200)
- **Complexity:** Not in code; removed. (src/geosync/regime/ews.py:1-215)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/regime/ews.py:1-200)

---

## Protocol Geometry (`src/geosync/protocol`)

### Div/Conv geometry (`src/geosync/protocol/divconv.py`)
- **Symbolic name:** Observed in code: gradients \(\nabla P_t, \nabla F_t\), angle \(\theta_t\), alignment \(\kappa_t\), divergence functional. (src/geosync/protocol/divconv.py:1-200)
- **Code location(s):** `src/geosync/protocol/divconv.py`. (src/geosync/protocol/divconv.py:1-274)
- **Type:** Observed in code: deterministic, discrete-time computations. (src/geosync/protocol/divconv.py:40-230)
- **Inputs/outputs:** Observed in code: price/flow sequences, optional times and metric; outputs scalar metrics and aggregated snapshot. (src/geosync/protocol/divconv.py:40-230)
- **Implicit assumptions:** Observed in code: times strictly increasing if provided; gradients finite. (src/geosync/protocol/divconv.py:40-110)
- **Known or suspected weaknesses:** Observed in code: thresholds \(\tau_d,\tau_c\) from quantiles. (src/geosync/protocol/divconv.py:150-190)

EVIDENCE:
- Functions/classes: `compute_price_gradient`, `compute_theta`, `compute_kappa`, `compute_divergence_functional`, `aggregate_signals`. (src/geosync/protocol/divconv.py:40-230)
- Constants/thresholds: `_EPS`, `alpha`/`beta` defaults in threshold helpers. (src/geosync/protocol/divconv.py:14-25, 150-190)
- Backend selection logic: none observed. (src/geosync/protocol/divconv.py:1-230)
- Input validation: finite checks and shape checks. (src/geosync/protocol/divconv.py:20-110, 120-160)

MATH CONTRACT:
- **Definition:** Observed in code: gradient via `np.gradient`, angle via normalized dot product, divergence via quadratic form. (src/geosync/protocol/divconv.py:40-140)
- **Domain:** Observed in code: finite arrays and increasing times. (src/geosync/protocol/divconv.py:40-80)
- **Range:** Observed in code: cosine clipped to [-1,1]. (src/geosync/protocol/divconv.py:70-110)
- **Invariants:** Observed in code: weight normalization uses L1 norm. (src/geosync/protocol/divconv.py:210-240)
- **Failure modes:** Observed in code: invalid inputs raise `ValueError`. (src/geosync/protocol/divconv.py:20-110)
- **Approximation notes:** PROXY: thresholds from empirical quantiles. (src/geosync/protocol/divconv.py:150-190)
- **Complexity:** Not in code; removed. (src/geosync/protocol/divconv.py:1-274)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/protocol/divconv.py:1-230)

---

## Drift Statistics (`src/geosync/utils`)

### Drift metrics (`src/geosync/utils/drift.py`)
- **Symbolic name:** Observed in code: Jensen–Shannon divergence, KS test, PSI. (src/geosync/utils/drift.py:1-200)
- **Code location(s):** `src/geosync/utils/drift.py`. (src/geosync/utils/drift.py:1-453)
- **Type:** Observed in code: deterministic statistics. (src/geosync/utils/drift.py:120-360)
- **Inputs/outputs:** Observed in code: numeric arrays/series; outputs divergence/test results. (src/geosync/utils/drift.py:120-360)
- **Implicit assumptions:** Observed in code: NaNs filtered; empty inputs return NaN. (src/geosync/utils/drift.py:120-200)
- **Known or suspected weaknesses:** Observed in code: binning affects PSI and JSD. (src/geosync/utils/drift.py:240-360)

EVIDENCE:
- Functions/classes: `compute_js_divergence`, `compute_ks_test`, `compute_psi`, `DriftMetric`. (src/geosync/utils/drift.py:120-360)
- Constants/thresholds: default thresholds in `DriftThresholds`. (src/geosync/utils/drift.py:50-100)
- Backend selection logic: none observed. (src/geosync/utils/drift.py:1-360)
- Input validation: finite checks and NaN filtering. (src/geosync/utils/drift.py:120-200)

MATH CONTRACT:
- **Definition:** Observed in code: JSD via SciPy distance squared, KS via `ks_2samp`, PSI via histogram ratios. (src/geosync/utils/drift.py:120-360)
- **Domain:** Observed in code: numeric arrays with finite values (NaNs removed). (src/geosync/utils/drift.py:120-200)
- **Range:** Observed in code: returns NaN for empty or degenerate inputs. (src/geosync/utils/drift.py:140-200)
- **Invariants:** Observed in code: drift flags computed from thresholds. (src/geosync/utils/drift.py:70-110)
- **Failure modes:** Observed in code: insufficient data returns invalid KS result. (src/geosync/utils/drift.py:200-230)
- **Approximation notes:** PROXY: PSI and JSD use discrete bins. (src/geosync/utils/drift.py:240-360)
- **Complexity:** Not in code; removed. (src/geosync/utils/drift.py:1-453)
- **Determinism:** Observed in code: no RNG usage. (src/geosync/utils/drift.py:1-360)
