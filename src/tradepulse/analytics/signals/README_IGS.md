IGS quantifies time-irreversibility in financial time series by combining entropy production, probability fluxes, time-reversal
asymmetry, and permutation entropy. The resulting metrics can be used as standalone regime indicators or gating signals for existing strategies.

## Key Metrics
- **EPR** – entropy production rate estimated from quantised return transitions.
- **Flux index** – signed collapse of antisymmetric probability fluxes.
- **TRA** – third-order statistic capturing time-reversal asymmetry with an exact rolling update.
- **Permutation entropy** – Bandt–Pompe entropy maintained incrementally after the warmup window.
- **Regime score** – weighted mean of `log1p(EPR)`, `|flux|`, and `(1 - PE)`.

### Choosing `pi_method`
- `empirical` keeps the historical behaviour by normalising row counts of the transition matrix. This is a good default when the sampling window is long enough and you want EPR to react to recent occupancy shifts.
- `stationary` solves the constrained system `pi = pi @ P` (with Tikhonov regularisation in the least-squares step) to obtain the stationary distribution implied by the current transition probabilities. This is numerically robust for sparse counts and suppresses transient sampling bias in EPR/flux calculations.

### Quantisation modes
- `quantize_mode="zscore"` (default) keeps an `O(1)` rolling mean/std and maps values to states via Gaussian quantiles.
- `quantize_mode="rank"` maintains a sliding window of historical returns backed by a deque and sorted array. Each update performs `O(log W)` search and `O(W)` data movement to keep the order statistics consistent, ensuring that the state at time `t` depends only on the past `W` returns.
  The rank quantiser centres empirical percentiles so that freshly initialised buffers (or post-gap rebuilds) start from the neutral bucket instead of saturating at the extremes, keeping batch and streaming pipelines aligned.

### Regime score weighting
- `regime_weights` controls the contribution of `[log1p(EPR), |flux|, 1 - PE]` in both batch and streaming pipelines.
- Weights are normalised after discarding NaN components; zero weights effectively drop a metric (e.g. ignore flux during calibration).
- When a component is degraded (e.g. permutation entropy under latency pressure), it is excluded from the weighted mean automatically.

## Python API
```python
from analytics.signals.irreversibility import (
    IGSConfig,
    StreamingIGS,
    compute_igs_features,
    igs_directional_signal,
)

cfg = IGSConfig(window=600, n_states=7)
features = compute_igs_features(price_series, cfg)
signal = igs_directional_signal(features, cfg=cfg)
```

### Configuration constraints

`IGSConfig` validates inputs to avoid degenerate parameterisations:

- `window >= 3` and `1 <= min_counts <= window` ensure rolling statistics warm up without degeneracy.
- `window >= (perm_emb_dim - 1) * perm_tau + 1` guarantees that permutation patterns are well-defined within each rolling window.
- `n_states >= 2`, `k_min >= 2`, and `k_min <= k_max` maintain valid Markov chains, and the initial `n_states` must satisfy
  `k_min <= n_states <= k_max` so that the Markov discretisation starts inside the adaptation corridor.
- `perm_emb_dim >= 3` and `perm_tau >= 1` keep the permutation entropy well-defined.
- `adapt_method` ∈ `{"off", "entropy", "external"}`, `quantize_mode` ∈ `{"zscore", "rank", "sliding_rank"}`, and `pi_method` ∈ `{"empirical", "stationary"}`.
- `regime_weights` must have three non-negative entries with at least one positive weight.
- `eps > 0`, `max_update_ms >= 0`, `0 < signal_epr_q < 1`, and `signal_flux_min >= 0` prevent ill-posed signal gating.

For streaming scenarios the quantiser, permutation entropy, and TRA updates are all `O(1)` after warmup:
```python
stream = StreamingIGS(cfg)
metrics = stream.update(timestamp, price)
if metrics is not None:
    process(metrics)
```

### Handling data gaps

- Prices that are missing, NaN, or non-positive mark a hard segmentation point for both batch (`compute_igs_features`) and streaming engines.
- The batch computation drops any window that would span a gap and rebuilds its quantiser/permutation-entropy buffers so that post-gap samples start from a clean history.
- The streaming reset clears cached returns, Markov states, and transition counts so that the next valid observation starts with a fresh window.
- Rolling statistics (TRA, permutation entropy) and the active quantiser are reinitialised alongside the K-adaptation controller, preventing "stitched" transitions across the gap.
- Metrics are therefore suppressed until the window accumulates the configured `min_counts` of post-gap transitions, keeping batch and streaming outputs aligned.
- Streaming updates expect strictly increasing timestamps. If a new tick arrives with a timestamp that is not greater than the previous one, the engine logs a warning, clears all buffers, and waits for the next monotonic sample. Downstream feeds should pre-sort data or drop out-of-order ticks before calling `StreamingIGS.update`.

## Pipeline Integration
Use the adapter for TradePulse pipelines:
```python
from analytics.signals.irreversibility_adapter import IGSFeatureProvider

provider = IGSFeatureProvider({"window": 600, "n_states": 7})
features = provider.compute_from_df(dataframe)
```
`IGSFeatureProvider.streaming_update` exposes incremental metrics suitable for low-latency ingestion or feature store updates.

## Adaptation & Monitoring
- `adapt_method="entropy"` enables hysteretic K adaptation with cooldown and optional external signals.
- When K changes the streaming engine performs a one-off `O(window)` rebuild to realign the quantiser and transition counts.
- Optional Prometheus gauges (`igs_epr`, `igs_flux_index`, `igs_regime_score`, `igs_states_k`) can be emitted inline or via a background worker.
- Set `prometheus_enabled=True` to instantiate the gauges. With `prometheus_async=False` the gauges are updated on the streaming thread, which keeps deployment simple for low-volume feeds. Switch on `prometheus_async=True` to offload emission to a background queue when you need to cap update latency.
- `max_update_ms` guards latency-sensitive deployments by degrading permutation entropy first.

## Validation Strategy
- Compare EPR/flux distributions on synthetic reversible vs. directional series.
- Cross-check streaming outputs against batch results on the same window.
- Run walk-forward backtests gated by `regime_score` and perform block-bootstrap statistics on performance deltas.

## Limitations
- The incremental permutation entropy rebuilds the multiset when the window changes size; this is still `O(window)` but amortised by the warmup period.
- Adaptation currently supports entropy and external measures; additional strategies can be hooked into `_KAdaptController`.
- The sliding rank quantiser trades latency for leak-free discretisation. Insert/delete operations shift elements inside the sorted buffer (`O(window)`), which is acceptable for typical windows (≤ 1e3) but should be benchmarked for significantly larger sizes.
