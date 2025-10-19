import numpy as np
import pandas as pd

from analytics.signals.irreversibility import IGSConfig, StreamingIGS


def test_streaming_igs_resets_on_non_monotonic_timestamp():
    cfg = IGSConfig(window=10, min_counts=3)
    engine = StreamingIGS(cfg)

    t0 = pd.Timestamp("2024-01-01T00:00:00Z")
    t1 = t0 + pd.Timedelta(minutes=1)

    assert engine.update(t0, 100.0) is None
    assert engine.update(t1, 101.0) is None
    assert engine.last_timestamp == t1

    regression_metrics = engine.update(t0, 102.0)

    assert regression_metrics is None
    assert engine.last_timestamp is None
    assert engine.last_price is None
    assert not engine.returns
    assert not engine.states
    assert np.all(engine.T == 0.0)
    assert np.all(engine.row_sums == 0.0)
