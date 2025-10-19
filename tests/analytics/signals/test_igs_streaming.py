import numpy as np
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, StreamingIGS


def test_streaming_resets_on_infinite_price() -> None:
    cfg = IGSConfig(window=32, n_states=5, min_counts=16, quantize_mode="zscore")
    engine = StreamingIGS(cfg)

    t0 = pd.Timestamp("2024-01-01T00:00:00Z")
    t1 = t0 + pd.Timedelta(minutes=1)
    t2 = t0 + pd.Timedelta(minutes=2)

    assert engine.update(t0, 101.0) is None
    assert engine.last_price is not None

    metric_after_inf = engine.update(t1, float("inf"))
    assert metric_after_inf is None
    assert engine.last_price is None
    assert engine.prev_state is None
    assert len(engine.returns) == 0
    assert len(engine.states) == 0
    assert float(engine.row_sums.sum()) == 0.0
    assert np.all(engine.T == 0.0)
    assert engine.tra_roll.n_pairs == 0
    assert engine.pe_roll.total == 0

    assert engine.update(t2, 103.0) is None
    assert engine.last_price == 103.0
