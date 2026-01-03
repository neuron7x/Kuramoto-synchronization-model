# Mathematical Inventory (Phase 0)

This inventory enumerates math-bearing components discovered in the current codebase. Entries are limited to what is explicitly implemented in code and documented in docstrings or validations.

## Scope
- `core/indicators/`
- `core/neuro/`
- `execution/risk/`
- `src/tradepulse/core/neuro/`
- `src/tradepulse/features/`
- `src/tradepulse/protocol/`
- `src/tradepulse/regime/`
- `src/tradepulse/risk/`
- `src/tradepulse/utils/`

---

## Core Indicators (`core/indicators`)

### Kuramoto phase and order parameter
- **Symbolic name:** Phase θ, analytic signal phase; order parameter \(R(t) = |\frac{1}{N}\sum_{j=1}^N e^{i\theta_j(t)}|\).
- **Code location(s):** `core/indicators/kuramoto.py` (`compute_phase`, `kuramoto_order`, `multi_asset_kuramoto`, `compute_phase_gpu`, `KuramotoOrderFeature`, `MultiAssetKuramotoFeature`); `core/indicators/trading.py` (`KuramotoIndicator`).
- **Type:** Deterministic, discrete-time, batch/streaming.
- **Inputs/outputs:**
  - Inputs: 1D/2D price or return arrays, optional weights; optional GPU arrays.
  - Outputs: phase array in radians; order parameter in \([0, 1]\).
- **Implicit assumptions:**
  - Inputs are numeric and finite (non-finite values filtered for order parameter).
  - Phase computation uses Hilbert/FFT; data length sufficient for transforms.
- **Known or suspected weaknesses:**
  - Optional SciPy/CuPy dependencies change backend behavior; fallback FFT path used when SciPy unavailable.
  - Order parameter clamps/thresholds (e.g., denormal suppression) imply heuristic numerical guards.

### Multi-scale Kuramoto synchronization
- **Symbolic name:** Multi-scale \(R\) and cross-scale coherence.
- **Code location(s):** `core/indicators/multiscale_kuramoto.py` (`MultiScaleKuramoto`, `FractalResampler`, `MultiScaleResult`).
- **Type:** Deterministic, discrete-time, multi-timeframe aggregation.
- **Inputs/outputs:**
  - Inputs: time-indexed price series; timeframes (seconds); windows.
  - Outputs: per-timeframe \(R\), consensus \(R\), cross-scale coherence, dominant timeframe.
- **Implicit assumptions:**
  - Input index is `DatetimeIndex` and monotonic for resampling.
  - Resampling uses last/forward-fill; assumes missing data can be forward-filled.
- **Known or suspected weaknesses:**
  - Cross-scale coherence depends on resampling/forward-fill heuristics.
  - Uses optional SciPy for signal processing when available.

### Ricci curvature (Ollivier-Ricci) on price graphs
- **Symbolic name:** \(\kappa(u,v) = 1 - W(\mu_u, \mu_v) / d(u,v)\).
- **Code location(s):** `core/indicators/ricci.py` (`build_price_graph`, `local_distribution`, `ricci_curvature_edge`, `mean_ricci`, `MeanRicciFeature`).
- **Type:** Deterministic, discrete-time graph metric.
- **Inputs/outputs:**
  - Inputs: price arrays, graph parameters (delta, radius), optional networkx.
  - Outputs: edge curvature, mean curvature.
- **Implicit assumptions:**
  - Graph connectivity based on price similarity; shortest paths are finite or approximated.
  - Wasserstein-1 distance approximated; weights normalized.
- **Known or suspected weaknesses:**
  - Optional `networkx` dependency; fallback graph implementation in `core/indicators/ricci.py`.
  - JIT/GPU paths are optional; behavior can differ by backend.

### Temporal Ricci curvature and transition score
- **Symbolic name:** Temporal curvature trajectory; transition score from curvature deltas.
- **Code location(s):** `core/indicators/temporal_ricci.py` (`TemporalRicciAnalyzer`, `OllivierRicciCurvatureLite`, `PriceLevelGraph`, `TemporalRicciResult`).
- **Type:** Deterministic, discrete-time with sliding window.
- **Inputs/outputs:**
  - Inputs: price series, optional volume, graph parameters (bins, radius, alpha).
  - Outputs: temporal curvature, transition score, stability metrics.
- **Implicit assumptions:**
  - Price levels are discretized into bins; graph uses undirected edges.
  - Volume scaling uses configured modes (`none`, `linear`, `sqrt`, `log`).
- **Known or suspected weaknesses:**
  - Ollivier-Ricci is an approximation using lazy random walks and cached distributions.
  - Graph is lightweight (no `networkx`) for CI portability; may differ from full ORC implementations.

### Kuramoto-Ricci composite regime classifier
- **Symbolic name:** Phase classifier and signals from \(R\), curvature, transition score.
- **Code location(s):** `core/indicators/kuramoto_ricci_composite.py` (`KuramotoRicciComposite`, `TradePulseCompositeEngine`, `CompositeSignal`).
- **Type:** Deterministic, discrete-time decision logic.
- **Inputs/outputs:**
  - Inputs: `MultiScaleResult`, `TemporalRicciResult`, static Ricci scalar.
  - Outputs: market phase, confidence, entry/exit signals, risk multiplier.
- **Implicit assumptions:**
  - Thresholds are fixed constants passed to constructor.
  - Confidence and signals are clipped into bounded ranges.
- **Known or suspected weaknesses:**
  - Phase mapping is threshold-based with fixed constants.

### Hurst exponent (lag-differencing method)
- **Symbolic name:** \(H\) from \(\log \sigma(\tau) = H\log \tau + c\).
- **Code location(s):** `core/indicators/hurst.py` (`hurst_exponent`, `HurstFeature`); `core/indicators/trading.py` (`HurstIndicator`).
- **Type:** Deterministic, discrete-time estimator.
- **Inputs/outputs:**
  - Inputs: 1D price series, lag range or defaults.
  - Outputs: Hurst exponent \(H \in [0,1]\) (bounded in code).
- **Implicit assumptions:**
  - Series length is sufficient for lag range; returns finite values.
  - Uses pseudo-inverse for regression; assumes log-lag design matrix is well-conditioned.
- **Known or suspected weaknesses:**
  - Optional Numba/CUDA paths change performance; default backend selection depends on input length.

### Shannon entropy and delta entropy
- **Symbolic name:** \(H(P) = -\sum_i p_i \log p_i\), \(\Delta H\) on rolling windows.
- **Code location(s):** `core/indicators/entropy.py` (`entropy`, `delta_entropy`, `EntropyFeature`, `DeltaEntropyFeature`); `core/indicators/hierarchical_features.py` (`_shannon_entropy`).
- **Type:** Deterministic, discrete-time histogram estimator.
- **Inputs/outputs:**
  - Inputs: 1D numeric series, bin count, optional chunking and backends.
  - Outputs: entropy scalar, delta entropy scalar.
- **Implicit assumptions:**
  - Data is scaled to \([-1,1]\); bins represent a fixed discretization.
  - Non-finite values are filtered; empty inputs return 0.0.
- **Known or suspected weaknesses:**
  - Histogram-based entropy depends on bin choice; chunking averages entropy across chunks.
  - GPU/async backends are optional; results may vary with backend precision.

### Pivot detection and divergence
- **Symbolic name:** Local extrema (pivot highs/lows), divergence signals between series.
- **Code location(s):** `core/indicators/pivot_detection.py` (`detect_pivots`, `detect_pivot_divergences`, `PivotPoint`, `PivotDivergenceSignal`).
- **Type:** Deterministic, discrete-time pattern detection.
- **Inputs/outputs:**
  - Inputs: price series, indicator series, window sizes, tolerance, optional timestamps.
  - Outputs: pivot lists, divergence signal records.
- **Implicit assumptions:**
  - Inputs are 1D numeric sequences; timestamps (if provided) align in length.
  - Local extrema are identified via left/right window comparisons.
- **Known or suspected weaknesses:**
  - Fixed window and tolerance parameters are heuristic.
  - Divergence detection depends on normalization mode (z-score by default).

### Indicator normalization utilities
- **Symbolic name:** Z-score and min-max normalization maps.
- **Code location(s):** `core/indicators/normalization.py` (`normalize_indicator_series`, `IndicatorNormalizationConfig`).
- **Type:** Deterministic, discrete-time transform.
- **Inputs/outputs:**
  - Inputs: 1D indicator series; config (mode, epsilon, feature range).
  - Outputs: normalized series (1D numpy array).
- **Implicit assumptions:**
  - Input is one-dimensional; standard deviation or min-max span can be zero.
- **Known or suspected weaknesses:**
  - Zero-variance input collapses to zeros or mid-point (for min-max), a heuristic fallback.

### Ensemble divergence aggregation
- **Symbolic name:** Weighted consensus score for divergences.
- **Code location(s):** `core/indicators/ensemble_divergence.py` (`compute_ensemble_divergence`, `EnsembleDivergenceResult`).
- **Type:** Deterministic, discrete-time aggregation.
- **Inputs/outputs:**
  - Inputs: divergence signals with strengths/confidence.
  - Outputs: consensus kind, score \([-1,1]\), support metrics.
- **Implicit assumptions:**
  - Strengths are non-negative; confidences in \([0,1]\).
  - Consensus thresholds (`min_support`, `min_consensus`) gate signal emission.
- **Known or suspected weaknesses:**
  - Thresholds are fixed constants (heuristic gating).

### Hierarchical feature computation
- **Symbolic name:** Multi-timeframe features (entropy, Hurst, Kuramoto, microstructure metrics).
- **Code location(s):** `core/indicators/hierarchical_features.py` (`compute_hierarchical_features`).
- **Type:** Deterministic, discrete-time multi-timeframe aggregation.
- **Inputs/outputs:**
  - Inputs: OHLCV data per timeframe, optional order book data.
  - Outputs: feature dictionary, phase coherence, benchmark metrics.
- **Implicit assumptions:**
  - OHLCV frames contain a `close` column; indices are convertible to `DatetimeIndex`.
  - Internal entropy uses fixed bin count and scaling.
- **Known or suspected weaknesses:**
  - Internal entropy estimator uses fixed bins and scaling constants.

### Fractal graph contrastive learning helpers
- **Symbolic name:** Fractal dimension \(D\), contrastive loss with fractal weighting.
- **Code location(s):** `core/indicators/fractal_gcl.py` (`fractal_boxcover`, `fd_one_shot`, `contrastive_loss_fractal`, `fractal_gcl_novelty`).
- **Type:** Deterministic for FD/novelty; stochastic gradient when used in learning.
- **Inputs/outputs:**
  - Inputs: networkx graph, embeddings, box size, temperature \(\tau\).
  - Outputs: fractal dimension estimate, novelty score, contrastive loss tensor.
- **Implicit assumptions:**
  - Graph is connected enough for shortest paths; embeddings are 2D arrays.
- **Known or suspected weaknesses:**
  - Contrastive loss requires PyTorch; behavior depends on optional dependency.

### Novelty scores (KL divergence, cosine distance)
- **Symbolic name:** \(D_{KL}(p\|q)\), \(1-\cos(\theta)\) between embeddings.
- **Code location(s):** `core/indicators/novelty.py` (`kl_div`, `novelty_score`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: probability vectors or embeddings.
  - Outputs: KL divergence scalar; cosine-based novelty scalar.
- **Implicit assumptions:**
  - Inputs are non-negative; vectors are normalized with clipping.
- **Known or suspected weaknesses:**
  - Uses fixed clipping constants (e.g., `1e-8`) for stability.

### Trading indicator wrappers (Kuramoto, Hurst, VPIN)
- **Symbolic name:** \(R(t)\) for Kuramoto, \(H\) for Hurst, VPIN.
- **Code location(s):** `core/indicators/trading.py` (`KuramotoIndicator`, `HurstIndicator`, `VPINIndicator`).
- **Type:** Deterministic, discrete-time rolling estimators.
- **Inputs/outputs:**
  - Inputs: price series (Kuramoto/Hurst), volume buckets (VPIN).
  - Outputs: indicator arrays (per-window values).
- **Implicit assumptions:**
  - Rolling windows are sized to data length; missing data filled.
  - VPIN uses volume bucket aggregation with optional GPU kernel.
- **Known or suspected weaknesses:**
  - GPU path is optional; kernel behavior differs with CUDA availability.

---

## Neuro Subsystems (core/neuro)

### Adaptive Market Mind (AMM)
- **Symbolic name:** Precision-weighted prediction error \(\delta_t = \pi_t (x_t - \hat{x}_t)\) with homeostatic gain control.
- **Code location(s):** `core/neuro/amm.py` (`AdaptiveMarketMind`, `AMMConfig`).
- **Type:** Deterministic, discrete-time dynamical system.
- **Inputs/outputs:**
  - Inputs: return observation, Kuramoto \(R\), Ricci \(\kappa\), optional entropy.
  - Outputs: pulse, precision, prediction error, entropy.
- **Implicit assumptions:**
  - EWMA parameters are in valid ranges; entropy defaults to internal estimator if not provided.
  - Precision is clipped to configured \([\pi_{min}, \pi_{max}]\).
- **Known or suspected weaknesses:**
  - Uses exponential/logistic transformations and fixed gains; sensitivity depends on configured constants.

### Streaming exponential-weighted features
- **Symbolic name:** EMA, EW variance, EW entropy, EW momentum, EW z-score, EW skewness.
- **Code location(s):** `core/neuro/features.py` (`ema_update`, `ewvar_update`, `EWEntropy`, `EWMomentum`, `EWZScore`, `EWSkewness`).
- **Type:** Deterministic, discrete-time streaming updates.
- **Inputs/outputs:**
  - Inputs: sequential observations, decay parameters.
  - Outputs: updated statistics (scalar).
- **Implicit assumptions:**
  - Parameters (spans, decay, eps) are valid ranges (validated in constructors).
  - EW entropy uses fixed binning and explicit bounds.
- **Known or suspected weaknesses:**
  - Fixed bin ranges for entropy may be misaligned with out-of-range data.

### Streaming quantile estimation
- **Symbolic name:** Quantile \(q_p\) using exact order statistics or P² algorithm.
- **Code location(s):** `core/neuro/quantile.py` (`ExactQuantile`, `P2Algorithm`).
- **Type:** Deterministic, discrete-time estimator; approximate for P².
- **Inputs/outputs:**
  - Inputs: stream of scalar observations, target quantile \(p\in(0,1)\).
  - Outputs: quantile estimate.
- **Implicit assumptions:**
  - Observations are finite; P² initialized after 5 observations.
- **Known or suspected weaknesses:**
  - P² algorithm provides approximation; exact error bounds not encoded in code.

### Position sizing and allocation
- **Symbolic name:** Volatility-targeted sizing \(w \propto \frac{\sigma_{target}}{\hat{\sigma}}\) with pulse/precision modulation; Kelly fraction.
- **Code location(s):** `core/neuro/sizing.py` (`position_size`, `kelly_size`, `risk_parity_weight`, `pulse_weight`, `precision_weight`, `SizerConfig`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: direction, precision, pulse, volatility estimate, config.
  - Outputs: leverage multiplier or allocation weight.
- **Implicit assumptions:**
  - Volatility estimates are non-negative; configuration validated to be positive.
  - Kelly fraction uses win/loss expectations and probability in (0,1).
- **Known or suspected weaknesses:**
  - Log-sigmoid precision mapping uses fixed constants and safe minima.

### Fractal analytics
- **Symbolic name:** Rescaled range \(R/S\), Hurst exponent \(H\), fractal dimension \(D = 2 - H\), multiscale energy.
- **Code location(s):** `core/neuro/fractal.py` (`rescaled_range`, `hurst_exponent`, `fractal_dimension_from_hurst`, `multiscale_energy`, `summarise_fractal_properties`).
- **Type:** Deterministic, discrete-time estimator.
- **Inputs/outputs:**
  - Inputs: 1D numeric series, window sizes.
  - Outputs: scalar estimates and `FractalSummary`.
- **Implicit assumptions:**
  - Input series is finite and long enough for selected window sizes.
- **Known or suspected weaknesses:**
  - Uses fixed small constants for numerical stability (e.g., epsilons).

### Fractal regulator
- **Symbolic name:** Fractal metrics (Hurst, PLE) and energy-based regulation.
- **Code location(s):** `core/neuro/fractal_regulator.py` (`EEPFractalRegulator`, `RegulatorMetrics`).
- **Type:** Deterministic, discrete-time controller.
- **Inputs/outputs:**
  - Inputs: scalar signal stream.
  - Outputs: metrics (hurst, ple, csi, energy, efficiency), regulator state.
- **Implicit assumptions:**
  - Sliding windows for metrics; internal normalization and scaling.
- **Known or suspected weaknesses:**
  - Uses thresholds and scaling constants embedded in configuration.

### ECS-inspired regulator
- **Symbolic name:** Adaptive risk threshold with Lyapunov-like stability metrics; Kalman filtering; conformal prediction intervals.
- **Code location(s):** `core/neuro/ecs_regulator.py` (`ECSInspiredRegulator`, `ECSMetrics`, `StabilityMetrics`).
- **Type:** Deterministic, discrete-time control system with optional stochastic inputs.
- **Inputs/outputs:**
  - Inputs: stress series, volatility, predicted/realized signals.
  - Outputs: risk thresholds, action gating decisions, stability metrics.
- **Implicit assumptions:**
  - Parameters validated for stability (positive thresholds, multipliers).
  - Monotonic free-energy descent enforced when enabled.
- **Known or suspected weaknesses:**
  - Contains fixed stability constants and thresholds (explicitly defined at module scope).

### Motivation and bandit logic
- **Symbolic name:** Softmax bandit selection, intrinsic reward, information gain.
- **Code location(s):** `core/neuro/motivation.py` (`FractalBandit`, `FractalMotivationEngine`, `AllostaticRegulator`, `ValuePredictor`, `FractalMotivationController`).
- **Type:** Deterministic with stochasticity only via inputs; discrete-time control.
- **Inputs/outputs:**
  - Inputs: motivation signals, rewards, state vectors.
  - Outputs: selected strategies, motivation decisions, intrinsic rewards.
- **Implicit assumptions:**
  - Inputs are finite arrays; softmax uses stable normalization.
- **Known or suspected weaknesses:**
  - Softmax temperature and update rates are configuration-driven constants.

### Shock scenario generator
- **Symbolic name:** Stochastic shock distribution parameterized by neural policy.
- **Code location(s):** `core/neuro/shocks.py` (`ShockScenarioGenerator`, `ShockScenario`).
- **Type:** Stochastic.
- **Inputs/outputs:**
  - Inputs: feature dimension, training steps, batch size.
  - Outputs: synthetic shock scenarios (magnitude, decay, duration).
- **Implicit assumptions:**
  - Requires PyTorch for training path; fallback class exists when unavailable.
- **Known or suspected weaknesses:**
  - Distributional assumptions embedded in the learned policy; depends on optional dependency.

### Calibration (random search)
- **Symbolic name:** Random search over parameter space for AMM.
- **Code location(s):** `core/neuro/calibration.py` (`calibrate_random`, `CalibConfig`, `CalibResult`).
- **Type:** Stochastic optimization.
- **Inputs/outputs:**
  - Inputs: parameter ranges, evaluation function, seed.
  - Outputs: best configuration and score.
- **Implicit assumptions:**
  - Objective is measurable from trace; random sampling assumes independent parameter draws.
- **Known or suspected weaknesses:**
  - Uses randomized search without gradient information; evaluation depends on chosen objective.

---

## Execution Risk (`execution/risk`)

### Execution risk limits and kill-switch logic
- **Symbolic name:** Constraint set on position, notional, order-rate, drawdown; kill-switch state.
- **Code location(s):** `execution/risk/core.py` (`RiskLimits`, `RiskManager`).
- **Type:** Deterministic, discrete-time constraint enforcement.
- **Inputs/outputs:**
  - Inputs: positions, notionals, order flow rate, drawdown values.
  - Outputs: approvals/violations, kill-switch state.
- **Implicit assumptions:**
  - Limits are validated (non-negative, bounds for drawdown in (0,1]).
- **Known or suspected weaknesses:**
  - Kill-switch thresholds are fixed constants inside `RiskLimits`.

---

## TradePulse Core Neuro (`src/tradepulse/core/neuro`)

### Dopamine controller and action gate
- **Symbolic name:** TD(0) reward prediction error (RPE), action gating via thresholds.
- **Code location(s):** `src/tradepulse/core/neuro/dopamine/dopamine_controller.py` (`DopamineController`, `DopamineConfig`); `src/tradepulse/core/neuro/dopamine/action_gate.py` (`ActionGate`); `src/tradepulse/core/neuro/dopamine/ddm_adapter.py` (`ddm_thresholds`, `DDMThresholds`).
- **Type:** Deterministic, discrete-time stochastic-control logic.
- **Inputs/outputs:**
  - Inputs: rewards, value estimates, novelty, performance metrics.
  - Outputs: RPE, tonic/phasic dopamine levels, gate decisions, temperature.
- **Implicit assumptions:**
  - Configuration parameters validated (threshold monotonicity, clipping ranges).
  - Logistic transforms use finite clipping bounds.
- **Known or suspected weaknesses:**
  - Thresholds and decay parameters are fixed constants in configuration.

### GABA inhibition gate
- **Symbolic name:** Inhibition coefficient from impulse trace and RPE-driven plasticity.
- **Code location(s):** `src/tradepulse/core/neuro/gaba/gaba_inhibition_gate.py` (`GABAInhibitionGate`, `GABAConfig`).
- **Type:** Deterministic, discrete-time controller.
- **Inputs/outputs:**
  - Inputs: impulse drive, stress, RPE.
  - Outputs: inhibition level \([0, 0.99]\).
- **Implicit assumptions:**
  - EMA decays and STDP weights are within validated bounds.
- **Known or suspected weaknesses:**
  - STDP and inhibition gains are constant configuration values.

### NA/ACh neuromodulator
- **Symbolic name:** Arousal/attention update with linear gains and clamping.
- **Code location(s):** `src/tradepulse/core/neuro/na_ach/neuromods.py` (`NAACHNeuromodulator`, `NAACHConfig`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: volatility, novelty.
  - Outputs: arousal, attention, risk multiplier, temperature scale.
- **Implicit assumptions:**
  - Inputs are non-negative (clamped); risk/temperature outputs are clamped to configured ranges.
- **Known or suspected weaknesses:**
  - Linear gain model and clamp bounds are fixed configuration parameters.

### Serotonin risk inhibition controller
- **Symbolic name:** Logistic inhibition \(\sigma(k(x-\theta))\) with phasic bursts and desensitization.
- **Code location(s):** `src/tradepulse/core/neuro/serotonin/serotonin_controller.py` (`SerotoninController`, `SerotoninConfig`).
- **Type:** Deterministic, discrete-time controller with meta-adaptation.
- **Inputs/outputs:**
  - Inputs: volatility, free energy, losses, risk metrics.
  - Outputs: gating decisions (hold/veto), inhibition level, temperature floor.
- **Implicit assumptions:**
  - Config parameters are validated via Pydantic bounds.
  - Meta-adaptation uses gradient-descent-style updates with bounded parameters.
- **Known or suspected weaknesses:**
  - Numerous fixed thresholds (cooldown, phase thresholds) encoded in config.

### NaK homeostatic controller
- **Symbolic name:** Softsign/PI control with gating and drawdown-sensitive inhibition.
- **Code location(s):** `src/tradepulse/core/neuro/nak/controller.py` (`NaKControllerV4_2`, `NaKConfig`).
- **Type:** Deterministic, discrete-time dynamical system.
- **Inputs/outputs:**
  - Inputs: performance proxy \(p\), volatility \(v\), drawdown, features.
  - Outputs: final risk mode scalar and diagnostic log.
- **Implicit assumptions:**
  - Drawdown is clamped to \([-1, \infty)\); thresholds fixed in config.
  - Uses exponential/logistic transforms with stability epsilon.
- **Known or suspected weaknesses:**
  - Gating thresholds and burst detection (z-score) rely on fixed constants.

---

## TradePulse Features (`src/tradepulse/features`)

### Kuramoto synchrony adapter
- **Symbolic name:** \(R(t) = |\langle e^{i\theta}\rangle|\), \(\Delta R\).
- **Code location(s):** `src/tradepulse/features/kuramoto.py` (`KuramotoSynchrony`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: price DataFrame (T  N), window, lag.
  - Outputs: order parameter series, \(\Delta R\), labels.
- **Implicit assumptions:**
  - Index is `DatetimeIndex`; window size less than series length.
- **Known or suspected weaknesses:**
  - Phase computation uses a simplified arctan proxy; docstring notes this is a simplification relative to Hilbert transform.
  - Labeling uses rolling medians and IQR thresholds (heuristic).

### Ricci curvature graph adapter
- **Symbolic name:** Approximate Ollivier-Ricci curvature on correlation graphs.
- **Code location(s):** `src/tradepulse/features/ricci.py` (`RicciCurvatureGraph`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: returns DataFrame, correlation threshold, window, \(\alpha\).
  - Outputs: edge curvatures and minimum curvature.
- **Implicit assumptions:**
  - Correlation graph edges created with absolute correlation \(\ge\) threshold.
  - Shortest path distances used in W-distance approximation.
- **Known or suspected weaknesses:**
  - Uses simplified Wasserstein approximation; disconnected graphs use large fallback distance (10.0).

### Topological sentinel (TDA)
- **Symbolic name:** Persistent homology score or proxy eigenvalue-based score.
- **Code location(s):** `src/tradepulse/features/topo.py` (`TopoSentinel`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: returns DataFrame, window, persistence threshold.
  - Outputs: `topo_score` scalar.
- **Implicit assumptions:**
  - Requires at least two assets with non-zero variance; cleans NaNs.
  - When Gudhi unavailable, uses proxy metrics (eigen spectrum, clustering proxy).
- **Known or suspected weaknesses:**
  - Fallback path is a heuristic proxy and not full persistent homology.

### Causal guard (transfer entropy / Granger)
- **Symbolic name:** Transfer entropy \(TE(X\to Y)\) via histogram discretization; Granger causality (optional).
- **Code location(s):** `src/tradepulse/features/causal.py` (`CausalGuard`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: DataFrame with target + drivers; max lag; bin count.
  - Outputs: Boolean TE pass flag.
- **Implicit assumptions:**
  - Histogram-based TE uses fixed binning; data is forward/back filled.
- **Known or suspected weaknesses:**
  - Granger test is optional; if statsmodels missing, only TE is used.

---

## TradePulse Risk and Regime

### Risk homeostasis (VaR/ES, Kelly shrinkage)
- **Symbolic name:** VaR/ES on losses; Kelly fraction \(f = \mu/\sigma^2\) with regime shrinkage.
- **Code location(s):** `src/tradepulse/risk/risk_core.py` (`var_es`, `kelly_shrink`, `compute_final_size`, `check_risk_breach`, `RiskConfig`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: returns array, confidence level \(\alpha\), regime labels, sizing hints.
  - Outputs: VaR/ES, Kelly fraction, final size, breach state.
- **Implicit assumptions:**
  - Returns are finite; non-finite values filtered.
  - VaR/ES computed on losses with \(L=-r\).
- **Known or suspected weaknesses:**
  - Regime mapping uses fixed multipliers (KILL/CAUTION/EMERGENT).

### Automated risk testing metrics
- **Symbolic name:** Max drawdown, Sharpe ratio, Monte Carlo returns.
- **Code location(s):** `src/tradepulse/risk/automated_testing.py` (`_calculate_max_drawdown`, `_calculate_sharpe_ratio`, `run_monte_carlo_simulation`, `validate_risk_metrics`).
- **Type:** Deterministic for metrics; stochastic for Monte Carlo.
- **Inputs/outputs:**
  - Inputs: returns arrays, risk-free rate, simulation configuration.
  - Outputs: metric scalars, stress test results.
- **Implicit assumptions:**
  - Monte Carlo draws are from normal distribution parameters derived from input returns.
- **Known or suspected weaknesses:**
  - Stress scenarios use fixed templates and parameters.

### Early Warning System (EWS)
- **Symbolic name:** Regime state logic on \(R\), \(\Delta R\), \(\kappa_{min}\), topo score, TE pass.
- **Code location(s):** `src/tradepulse/regime/ews.py` (`EWSAggregator`, `EWSConfig`).
- **Type:** Deterministic, discrete-time decision rule.
- **Inputs/outputs:**
  - Inputs: synchrony metrics, curvature, topological score, causal flag.
  - Outputs: regime label and confidence in \([0,1]\).
- **Implicit assumptions:**
  - Thresholds for \(\Delta R\), topology, and curvature are fixed or env-configured.
- **Known or suspected weaknesses:**
  - Decision logic is threshold-based and heuristic.

---

## TradePulse Protocol (`src/tradepulse/protocol`)

### Div/Conv geometry and aggregation
- **Symbolic name:** Gradients \(\nabla P_t, \nabla F_t\); alignment \(\kappa_t = \cos\theta_t\); divergence functional \(D\); thresholds \(\tau_d, \tau_c\).
- **Code location(s):** `src/tradepulse/protocol/divconv.py` (`compute_price_gradient`, `compute_theta`, `compute_kappa`, `compute_divergence_functional`, `compute_threshold_tau_d`, `compute_threshold_tau_c`, `aggregate_signals`).
- **Type:** Deterministic, discrete-time.
- **Inputs/outputs:**
  - Inputs: price/flow sequences, optional time grids, metric matrices, risk weights.
  - Outputs: gradients, angles, divergence scalars, aggregated snapshot.
- **Implicit assumptions:**
  - Gradients require at least two observations; times must be strictly increasing when provided.
  - Risk weights are finite; normalization uses L1 norm of weights.
- **Known or suspected weaknesses:**
  - Thresholds are quantile-based with fixed \(\alpha\), \(\beta\).

---

## TradePulse Utilities (`src/tradepulse/utils`)

### Drift statistics
- **Symbolic name:** Jensen–Shannon divergence, KS two-sample test, PSI.
- **Code location(s):** `src/tradepulse/utils/drift.py` (`compute_js_divergence`, `compute_ks_test`, `compute_psi`, `DriftMetric`).
- **Type:** Deterministic, discrete-time batch statistics.
- **Inputs/outputs:**
  - Inputs: numeric arrays or series; bin counts for PSI.
  - Outputs: divergence scalars, KS statistic/p-value, PSI.
- **Implicit assumptions:**
  - NaNs filtered; empty inputs return NaN and warnings.
  - For JSD, aligned arrays treated as probability vectors; otherwise empirical distributions.
- **Known or suspected weaknesses:**
  - PSI and JSD depend on binning and discretization choices.
