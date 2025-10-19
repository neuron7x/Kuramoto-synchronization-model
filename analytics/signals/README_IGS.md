Irreversibility-Gated Signal (IGS)
=================================

The Irreversibility-Gated Signal quantifies time-reversal asymmetry of a
financial time-series.  It is designed as an interpretable regime detector that
works alongside the existing `SignalFeaturePipeline` components in TradePulse.

Provided features
-----------------
For each window of log-returns the module emits five columns:

```
- epr          : entropy production rate of the Markov transition matrix
- flux_index   : signed probability flux summarising directional bias
- tra          : third-order time-reversal asymmetry statistic
- pe           : permutation entropy (Bandt-Pompe)
- regime_score : bounded [0, 1] composite score combining the metrics
```

The discretisation uses rank-based states, making the features scale-invariant
with respect to volatility changes.  `regime_score` emphasises irreversible and
directional behaviour while penalising high entropy states.

Batch usage
-----------
```python
from analytics.signals.irreversibility import IGSConfig, compute_igs_features

cfg = IGSConfig(window=600, n_states=7)
features = compute_igs_features(price_series, cfg)
```

Streaming usage
---------------
```python
from analytics.signals.irreversibility import IGSConfig, StreamingIGS

engine = StreamingIGS(IGSConfig(window=600, n_states=7))
for timestamp, price in stream:
    metrics = engine.update(timestamp, price)
    if metrics:
        signal = engine.get_signal(epr_threshold=0.15, flux_threshold=0.2)
```

Directional gating helper
-------------------------
```python
from analytics.signals.irreversibility import igs_directional_signal

signal = igs_directional_signal(features, epr_q=0.7, flux_q=0.6, regime_threshold=0.45)
```

Integration hints
-----------------
- Register `IGSFeatureProvider` with the analytics pipeline to append the
  features during feature engineering.
- Use `regime_score` as a gating or scaling variable for strategies; the sign of
  `flux_index` provides directional context.
- The streaming interface recomputes the rank-based discretisation on each
  update to match batch behaviour exactly.  For high-throughput deployments,
  profiling is recommended to ensure the chosen window size meets latency
  targets.

Testing
-------
The analytics test suite covers batch computations, streaming parity, and the
pipeline adapter:

```
python -m pytest tests/analytics/signals -q
```
