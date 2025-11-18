import numpy as np
import pandas as pd

from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine


def sample_df(n=1500):
    idx = pd.date_range("2024-01-01", periods=n, freq="1min")
    r1 = np.cumsum(np.random.normal(0, 0.6, n // 3))
    r2 = r1[-1] + 0.05 * np.arange(n // 3) + 2.5 * np.sin(2 * np.pi * np.arange(n // 3) / 100.0)
    r3 = r2[-1] + np.cumsum(np.random.normal(0, 1.2, n - 2 * (n // 3)))
    price = 100 + np.concatenate([r1, r2, r3])
    vol = np.random.lognormal(10, 1, n)
    return pd.DataFrame({"close": price, "volume": vol}, index=idx)


if __name__ == "__main__":
    df = sample_df()
    eng = TradePulseCompositeEngine()
    sig = eng.analyze_market(df)
    print("=== Kuramoto–Ricci Composite ===")
    print("Phase:", sig.phase.value)
    print("Confidence:", round(sig.confidence, 3), "Entry:", round(sig.entry_signal, 3))
