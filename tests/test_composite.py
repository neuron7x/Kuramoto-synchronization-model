import numpy as np
import pandas as pd

from core.indicators.kuramoto_ricci_composite import (
    MarketPhase,
    TradePulseCompositeEngine,
)


def synthetic_df(n: int = 1200, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    # multi-regime
    third = n // 3
    r1 = np.cumsum(rng.normal(0, 0.5, third))
    ramp = np.arange(third, dtype=float)
    r2 = r1[-1] + 0.03 * ramp + 2 * np.sin(2 * np.pi * ramp / 80.0)
    r3 = r2[-1] + np.cumsum(rng.normal(0, 1.0, n - 2 * third))
    price = 100 + np.concatenate([r1, r2, r3])
    vol = rng.lognormal(10, 1, n)
    return pd.DataFrame({"close": price, "volume": vol}, index=idx)


def test_end_to_end_runs():
    df = synthetic_df(900)
    eng = TradePulseCompositeEngine()
    sig = eng.analyze_market(df)
    assert sig.phase in MarketPhase
    assert np.isfinite(sig.kuramoto_R)
    assert np.isfinite(sig.temporal_ricci)
