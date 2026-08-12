from __future__ import annotations

import numpy as np
import pandas as pd

from src.kuramoto_trader.bridge.market_phase_live import MarketPhaseLive


def test_returns_none_during_warmup() -> None:
    m = MarketPhaseLive(window=8)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    for i in range(7):
        assert m.update(100 + i, ts + pd.Timedelta(hours=i)) is None


def test_returns_float_after_warmup() -> None:
    m = MarketPhaseLive(window=8)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    out = None
    for i in range(8):
        out = m.update(100 + np.sin(i), ts + pd.Timedelta(hours=i))
    assert isinstance(out, float)


def test_phase_bounded_minus_pi_to_pi() -> None:
    m = MarketPhaseLive(window=16)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    phases = []
    for i in range(30):
        p = m.update(100 + np.sin(i / 2), ts + pd.Timedelta(hours=i))
        if p is not None:
            phases.append(p)
    assert all(-np.pi <= p <= np.pi for p in phases)


def test_phase_series_length_matches_updates() -> None:
    m = MarketPhaseLive(window=4)
    ts = pd.Timestamp("2026-01-01", tz="UTC")
    for i in range(10):
        m.update(100 + i, ts + pd.Timedelta(hours=i))
    assert len(m.phase_series()) == 10
