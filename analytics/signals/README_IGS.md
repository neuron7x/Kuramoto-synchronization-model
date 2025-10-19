IGS quantifies time-irreversibility in financial time series by combining entropy production, probability fluxes, time-reversal
asymmetry, and permutation entropy. The resulting metrics can be used as standalone regime indicators or gating signals for existing strategies.

## Key Metrics
- **EPR** – entropy production rate estimated from quantised return transitions.
- **Flux index** – signed collapse of antisymmetric probability fluxes.
- **TRA** – third-order statistic capturing time-reversal asymmetry with an exact rolling update.
- **Permutation entropy** – Bandt–Pompe entropy maintained incrementally after the warmup window.
- **Regime score** – mean of `log1p(EPR)`, `|flux|`, and `(1 - PE)`.

### Choosing `pi_method`
- `empirical` keeps the historical behaviour by normalising row counts of the transition matrix. This is a good default when the sampling window is long enough and you want EPR to react to recent occupancy shifts.
- `stationary` solves the constrained system `pi = pi @ P` (with Tikhonov regularisation in the least-squares step) to obtain the stationary distribution implied by the current transition probabilities. This is numerically robust for sparse counts and suppresses transient sampling bias in EPR/flux calculations.

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
signal = igs_directional_signal(features, epr_q=0.7, flux_min=0.0)
```

For streaming scenarios the quantiser, permutation entropy, and TRA updates are all `O(1)` after warmup:
```python
stream = StreamingIGS(cfg)
metrics = stream.update(timestamp, price)
if metrics is not None:
    process(metrics)
```

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
- Optional Prometheus gauges (`igs_epr`, `igs_flux_index`, `igs_regime_score`, `igs_states_k`) are emitted asynchronously when enabled.
- `max_update_ms` guards latency-sensitive deployments by degrading permutation entropy first.

## Validation Strategy
- Compare EPR/flux distributions on synthetic reversible vs. directional series.
- Cross-check streaming outputs against batch results on the same window.
- Run walk-forward backtests gated by `regime_score` and perform block-bootstrap statistics on performance deltas.

## Limitations
- The incremental permutation entropy rebuilds the multiset when the window changes size; this is still `O(window)` but amortised by the warmup period.
- Adaptation currently supports entropy and external measures; additional strategies can be hooked into `_KAdaptController`.
