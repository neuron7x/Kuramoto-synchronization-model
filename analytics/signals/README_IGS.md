# Irreversibility-Gated Signal (IGS)

IGS quantifies time-irreversibility in financial time series by combining entropy production, probability fluxes, time-reversal asymmetry, and permutation entropy. The resulting metrics can be used as standalone regime indicators or gating signals for existing strategies.

## Key Metrics
- **EPR** – entropy production rate estimated from quantised return transitions.
- **Flux index** – signed collapse of antisymmetric probability fluxes.
- **TRA** – third-order statistic capturing time-reversal asymmetry.
- **Permutation entropy** – Bandt–Pompe entropy normalised to [0, 1].
- **Regime score** – weighted blend of `log1p(EPR)`, `|flux|`, and `(1 - PE)`.

## Python API
```python
from analytics.signals.irreversibility import (
    IGSConfig,
    compute_igs_features,
    igs_directional_signal,
    StreamingIGS,
)

cfg = IGSConfig(window=600, n_states=7)
features = compute_igs_features(price_series, cfg)
signal = igs_directional_signal(features, epr_q=0.7, flux_q=0.6)
```

For streaming scenarios:
```python
stream = StreamingIGS(cfg)
metrics = stream.update(timestamp, price)
if metrics is not None:
    do_something(metrics)
```

## Pipeline Integration
Use the adapter for TradePulse pipelines:
```python
from analytics.signals.irreversibility_adapter import IGSFeatureProvider

provider = IGSFeatureProvider({"window": 600, "n_states": 7})
features = provider.compute_from_frame(dataframe)
```
`IGSFeatureProvider.streaming_update` exposes incremental metrics suitable for low-latency ingestion or feature store updates.

## Validation Strategy
- Compare EPR/flux distributions on synthetic reversible vs. directional series.
- Cross-check streaming outputs against batch results on the same window.
- Run walk-forward backtests gated by `regime_score` and perform block-bootstrap statistics on performance deltas.

## Limitations
- The permutation entropy implementation recomputes counts per update (correct but `O(window)`). Optimise via incremental ordinal patterns if needed.
- `pi_method="eigen"` currently falls back to the empirical occupancy; enable eigenvalue iteration when latency budgets allow.
