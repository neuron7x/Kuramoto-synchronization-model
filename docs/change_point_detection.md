# Change point detection utilities

The `utils.change_point` module exposes lightweight helpers used by the FHMC
controller to surface abrupt shifts in streaming signals without introducing
heavy dependencies.

## `cusum_score`

`cusum_score(series, drift=0.0, threshold=5.0)` normalises a numeric sequence
and counts the number of cumulative-sum alarms triggered when positive or
negative deviations exceed the configured `threshold`. The accumulator resets
after each alarm so multiple shocks inside the same sequence are recorded.

Use this helper to raise alerts when a stable process suddenly drifts:

```python
from utils.change_point import cusum_score

alarms = cusum_score([0.0] * 10 + [10.0] * 5)
print(f"Detected {alarms} change points")
```

## `vol_shock`

`vol_shock(returns, window=60)` compares recent volatility to an earlier
baseline of the same length. It returns a positive value when the trailing
`window` samples are more volatile than the initial window, a negative value
when volatility compresses, and `0.0` if the series is too short to evaluate.

This metric is useful during market openings or other regimes where oscillation
intensity can shift quickly:

```python
from utils.change_point import vol_shock

shock = vol_shock([0, 1, 0, 0, 5, 0], window=3)
if shock > 0:
    print("Recent volatility is higher than the baseline")
```
